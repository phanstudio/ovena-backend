import json
import logging

from django.db.models import Count
from django.utils import timezone
from channels.db import database_sync_to_async

from menu.models import Order, OrderEvent, OrderStatus
from accounts.models import DriverProfile
from menu.websocket_utils import get_order_group_name, get_admin_group_name
from .base import BaseConsumer, CLOSE_FORBIDDEN, CLOSE_UNAUTHENTICATED

logger = logging.getLogger(__name__)

STUCK_ORDER_THRESHOLD_MINUTES = 15

ACTIVE_STATUSES = [
    OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PREPARING,
    OrderStatus.READY, OrderStatus.DRIVER_ASSIGNED, OrderStatus.PICKED_UP,
    OrderStatus.ON_THE_WAY,
]

PAYMENT_RISK_STATUSES = [
    OrderStatus.PAYMENT_PENDING, OrderStatus.AWAITING_PAYMENT_METHOD,
]


class AdminConsumer(BaseConsumer):
    """
    WebSocket consumer for the admin/ops dashboard.
    Gives full visibility into active orders, payment failures, stalled
    orders and cancellations, plus emergency controls (manual driver
    assignment, status override) for when something needs a human to
    step in.
    """

    async def connect_func(self):
        self.user = self.scope["user"]
        if not self.user or self.user.is_anonymous:
            await self.close(code=CLOSE_UNAUTHENTICATED)
            return

        is_admin = await self.check_is_admin(self.user)
        if not is_admin:
            await self.close(code=CLOSE_FORBIDDEN)
            return

        self.admin_group_name = get_admin_group_name()
        self._monitored_order_ids = set()

        await self.channel_layer.group_add(self.admin_group_name, self.channel_name)
        await self.join_active_order_groups()
        await self.accept()

        dashboard = await self.get_dashboard_snapshot()
        await self._send_json({'type': 'dashboard', 'data': dashboard})
        return True

    async def disconnect_func(self, close_code):
        if hasattr(self, "admin_group_name"):
            await self.channel_layer.group_discard(self.admin_group_name, self.channel_name)

        # Leave every per-order group we joined so channel-layer membership
        # doesn't grow unbounded across long admin sessions.
        for order_id in getattr(self, "_monitored_order_ids", ()):
            await self.channel_layer.group_discard(
                get_order_group_name(order_id), self.channel_name
            )

    async def receive_func(self, message_type, data):
        if message_type == 'request_dashboard':
            await self._send_json({'type': 'dashboard', 'data': await self.get_dashboard_snapshot()})

        elif message_type == 'request_failure_points':
            await self._send_json({'type': 'failure_points', 'data': await self.get_failure_points()})

        elif message_type == 'request_order_events':
            order_id = data.get('order_id')
            if order_id is None:
                await self._send_json({'type': 'error', 'message': 'order_id is required'})
                return
            events = await self.get_order_events(order_id)
            await self._send_json({'type': 'order_events', 'order_id': order_id, 'data': events})

        elif message_type == 'assign_driver':
            await self._handle_assign_driver(data)

        elif message_type == 'force_status':
            await self._handle_force_status(data)

        else:
            await self._send_json({'type': 'error', 'message': f'Unknown message type: {message_type}'})

    # ── group message handlers ──────────────────────────────────────────

    async def order_update(self, event):
        await self._send_json({'type': 'order.update', 'data': event['data']})

    async def branch_notification(self, event):
        await self._send_json({'type': 'branch_notification', 'data': event['data']})

    async def driver_notification(self, event):
        await self._send_json({'type': 'driver_notification', 'data': event['data']})

    async def admin_notification(self, event):
        """
        Generic channel for system-raised alerts, e.g. wiring
        tasks.mark_order_failed() to group_send(ADMIN_MONITORING_GROUP,
        {'type': 'admin_notification', 'data': {...}}) so a driver-matching
        exhaustion shows up on every open dashboard in real time.
        """
        await self._send_json({'type': 'admin_notification', 'data': event['data']})

    # ── emergency actions ────────────────────────────────────────────────

    async def _handle_assign_driver(self, data):
        order_id = data.get('order_id')
        driver_id = data.get('driver_id')
        if not order_id or not driver_id:
            await self._send_json({'type': 'error', 'message': 'order_id and driver_id are required'})
            return

        result = await self.assign_driver_to_order(order_id, driver_id)
        await self._send_json({'type': 'assign_driver_result', 'data': result})

        if result.get('ok'):
            await self.channel_layer.group_send(
                get_order_group_name(result['order_id']),
                {'type': 'order_update', 'data': {
                    'type': 'driver_assigned',
                    'driver_id': result['driver_id'],
                    'manual_override': True,
                }}
            )
            logger.info(
                "Admin %s manually assigned driver %s to order %s",
                self.user.id, driver_id, order_id,
            )

    async def _handle_force_status(self, data):
        order_id = data.get('order_id')
        new_status = data.get('status')
        reason = data.get('reason', '')

        valid_statuses = {c[0] for c in OrderStatus.choices}
        if new_status not in valid_statuses:
            await self._send_json({'type': 'error', 'message': f'Invalid status: {new_status}'})
            return

        result = await self.force_order_status(order_id, new_status, reason)
        await self._send_json({'type': 'force_status_result', 'data': result})

        if result.get('ok'):
            await self.channel_layer.group_send(
                get_order_group_name(order_id),
                {'type': 'order_update', 'data': {
                    'type': 'status_override',
                    'status': new_status,
                    'reason': reason,
                }}
            )
            logger.warning(
                "Admin %s forced order %s from %s to %s (%s)",
                self.user.id, order_id, result.get('old_status'), new_status, reason,
            )

    # ── DB helpers ──────────────────────────────────────────────────────

    async def join_active_order_groups(self):
        order_ids = await self.get_monitored_order_ids()
        for order_id in order_ids:
            await self.channel_layer.group_add(get_order_group_name(order_id), self.channel_name)
            self._monitored_order_ids.add(order_id)

    @database_sync_to_async
    def get_monitored_order_ids(self):
        return list(
            Order.objects.filter(
                status__in=ACTIVE_STATUSES + PAYMENT_RISK_STATUSES
            ).values_list('id', flat=True)
        )

    @database_sync_to_async
    def get_dashboard_snapshot(self):
        active_counts = (
            Order.objects.filter(status__in=ACTIVE_STATUSES)
            .values('status')
            .annotate(count=Count('id'))
        )

        stuck_threshold = timezone.now() - timezone.timedelta(minutes=STUCK_ORDER_THRESHOLD_MINUTES)
        stuck_orders_count = Order.objects.filter(
            status__in=ACTIVE_STATUSES,
            last_modified_at__lt=stuck_threshold,
        ).count()

        payment_failure_count = Order.objects.filter(
            status__in=PAYMENT_RISK_STATUSES,
            payment_retry_count__gte=1,
        ).count()

        cancelled_today = Order.objects.filter(
            status=OrderStatus.CANCELLED,
            last_modified_at__date=timezone.now().date(),
        ).count()

        return {
            'active_by_status': {row['status']: row['count'] for row in active_counts},
            'stuck_orders_count': stuck_orders_count,
            'payment_failure_count': payment_failure_count,
            'cancelled_today_count': cancelled_today,
            'generated_at': timezone.now().isoformat(),
        }

    @database_sync_to_async
    def get_failure_points(self):
        stuck_threshold = timezone.now() - timezone.timedelta(minutes=STUCK_ORDER_THRESHOLD_MINUTES)

        def _iso(row, *fields):
            for f in fields:
                if row.get(f):
                    row[f] = row[f].isoformat()
            return row

        stuck_payments = [
            _iso(r, 'last_payment_attempt', 'next_retry_at', 'created_at')
            for r in Order.objects.filter(status__in=PAYMENT_RISK_STATUSES)
            .order_by('-payment_retry_count', 'last_modified_at')
            .values('id', 'order_number', 'status', 'payment_retry_count',
                     'last_payment_attempt', 'next_retry_at', 'created_at')[:50]
        ]

        stalled_active = [
            _iso(r, 'last_modified_at')
            for r in Order.objects.filter(
                status__in=ACTIVE_STATUSES, last_modified_at__lt=stuck_threshold
            ).order_by('last_modified_at')
            .values('id', 'order_number', 'status', 'last_modified_at', 'branch__name')[:50]
        ]

        recent_cancellations = [
            _iso(r, 'timestamp')
            for r in OrderEvent.objects.filter(event_type='cancelled')
            .order_by('-timestamp')
            .values('order_id', 'order__order_number', 'timestamp', 'metadata', 'actor_type')[:50]
        ]

        return {
            'stuck_payments': stuck_payments,
            'stalled_active_orders': stalled_active,
            'recent_cancellations': recent_cancellations,
        }

    @database_sync_to_async
    def get_order_events(self, order_id):
        events = OrderEvent.objects.filter(order_id=order_id).order_by('-timestamp').values(
            'id', 'event_type', 'actor_type', 'actor_id',
            'old_status', 'new_status', 'metadata', 'timestamp',
        )
        return [
            {**e, 'timestamp': e['timestamp'].isoformat() if e['timestamp'] else None}
            for e in events
        ]

    @database_sync_to_async
    def assign_driver_to_order(self, order_id, driver_id):
        try:
            order = Order.objects.select_related('branch').get(id=order_id)
        except Order.DoesNotExist:
            return {'ok': False, 'error': 'order_not_found'}

        try:
            driver = DriverProfile.objects.get(id=driver_id)
        except DriverProfile.DoesNotExist:
            return {'ok': False, 'error': 'driver_not_found'}

        old_status = order.status
        order.driver = driver
        order.status = OrderStatus.DRIVER_ASSIGNED
        order.assigned_at = timezone.now()
        order.save(update_fields=['driver', 'status', 'assigned_at', 'last_modified_at'])

        driver.is_available = False
        driver.current_order = order
        driver.save(update_fields=['is_available', 'current_order'])

        OrderEvent.objects.create(
            order=order,
            event_type='driver_assigned',
            actor_type='admin',
            actor_id=self.user.id,
            old_status=old_status,
            new_status=OrderStatus.DRIVER_ASSIGNED,
            metadata={
                'driver_id': driver.id,
                'manual_override': True,
            },
        )

        return {
            'ok': True,
            'order_id': order.id,
            'order_number': order.order_number,
            'driver_id': driver.id,
            'branch_id': order.branch_id,
        }

    @database_sync_to_async
    def force_order_status(self, order_id, new_status, reason):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return {'ok': False, 'error': 'order_not_found'}

        old_status = order.status
        order.status = new_status
        order.save(update_fields=['status', 'last_modified_at'])

        OrderEvent.objects.create(
            order=order,
            event_type='admin_override',
            actor_type='admin',
            actor_id=self.user.id,
            old_status=old_status,
            new_status=new_status,
            metadata={'reason': reason},
        )

        return {'ok': True, 'order_id': order.id, 'old_status': old_status, 'new_status': new_status}
