import logging

from django.db.models import Count
from django.utils import timezone

from rest_framework import generics, status
from rest_framework.response import Response

from menu.models import Order, OrderEvent, OrderStatus
from accounts.models import DriverProfile
from menu.websocket_utils import broadcast_to_order_group, broadcast_to_admins
from menu.services.order_cancel import cancel_order, ACTORS

from .admin_serializers import (
    AdminOrderListSerializer, AdminOrderDetailSerializer, AdminOrderEventSerializer,
    AssignDriverSerializer, ForceStatusSerializer, CancelOrderSerializer,
)
from .views import BaseAppAdminAPIView

logger = logging.getLogger(__name__)

# Keep in sync with consumers/admin.py's ACTIVE_STATUSES / STUCK_ORDER_THRESHOLD_MINUTES
# until both are pulled from a shared constants module.
STUCK_THRESHOLD_MINUTES = 15

ACTIVE_STATUSES = [
    OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PREPARING,
    OrderStatus.READY, OrderStatus.DRIVER_ASSIGNED, OrderStatus.PICKED_UP,
    OrderStatus.ON_THE_WAY,
]

PAYMENT_RISK_STATUSES = [OrderStatus.PAYMENT_PENDING, OrderStatus.AWAITING_PAYMENT_METHOD]



class AdminOrderListView(BaseAppAdminAPIView, generics.ListAPIView):
    """
    GET /admin/orders/
    Query params: status, branch_id, stuck=true, payment_failures=true
    """
    serializer_class = AdminOrderListSerializer

    def get_queryset(self):
        qs = Order.objects.select_related('orderer', 'branch', 'driver').order_by('-created_at')

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        branch_id = self.request.query_params.get('branch_id')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        if self.request.query_params.get('stuck') == 'true':
            threshold = timezone.now() - timezone.timedelta(minutes=STUCK_THRESHOLD_MINUTES)
            qs = qs.filter(status__in=ACTIVE_STATUSES, last_modified_at__lt=threshold)

        if self.request.query_params.get('payment_failures') == 'true':
            qs = qs.filter(status__in=PAYMENT_RISK_STATUSES, payment_retry_count__gte=1)

        return qs


class AdminOrderDetailView(BaseAppAdminAPIView, generics.RetrieveAPIView):
    """GET /admin/orders/<id>/ — full order detail including event timeline."""
    serializer_class = AdminOrderDetailSerializer
    queryset = Order.objects.select_related('orderer', 'branch', 'driver').prefetch_related('events')


class AdminDashboardView(BaseAppAdminAPIView):
    """GET /admin/orders/dashboard/ — the counts behind the ops overview."""

    def get(self, request):
        active_counts = (
            Order.objects.filter(status__in=ACTIVE_STATUSES)
            .values('status').annotate(count=Count('id'))
        )
        threshold = timezone.now() - timezone.timedelta(minutes=STUCK_THRESHOLD_MINUTES)
        stuck_count = Order.objects.filter(
            status__in=ACTIVE_STATUSES, last_modified_at__lt=threshold
        ).count()
        payment_failure_count = Order.objects.filter(
            status__in=PAYMENT_RISK_STATUSES, payment_retry_count__gte=1
        ).count()
        cancelled_today = Order.objects.filter(
            status=OrderStatus.CANCELLED, last_modified_at__date=timezone.now().date()
        ).count()

        return Response({
            'active_by_status': {row['status']: row['count'] for row in active_counts},
            'stuck_orders_count': stuck_count,
            'payment_failure_count': payment_failure_count,
            'cancelled_today_count': cancelled_today,
            'generated_at': timezone.now().isoformat(),
        })


class AdminCancelledOrdersView(BaseAppAdminAPIView, generics.ListAPIView):
    """GET /admin/orders/cancelled/ — cancelled orders (join events for the 'why')."""
    serializer_class = AdminOrderListSerializer

    def get_queryset(self):
        return Order.objects.filter(
            status=OrderStatus.CANCELLED
        ).select_related('orderer', 'branch', 'driver').order_by('-last_modified_at')


class AdminOrderEventsView(BaseAppAdminAPIView, generics.ListAPIView):
    """GET /admin/orders/<order_id>/events/ — full audit trail for one order."""
    serializer_class = AdminOrderEventSerializer

    def get_queryset(self):
        return OrderEvent.objects.filter(order_id=self.kwargs['order_id']).order_by('-timestamp')


class AdminAssignDriverView(BaseAppAdminAPIView):
    """
    POST /admin/orders/<order_id>/assign-driver/  { "driver_id": 42 }
    Emergency manual override — bypasses the normal nearest-driver matching
    in tasks.find_and_assign_driver.
    """

    def post(self, request, order_id):
        serializer = AssignDriverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        driver_id = serializer.validated_data['driver_id']

        try:
            order = Order.objects.select_related('branch').get(id=order_id)
        except Order.DoesNotExist:
            return Response({'detail': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

        driver = DriverProfile.objects.get(id=driver_id)

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
            actor_id=request.user.id,
            old_status=old_status,
            new_status=OrderStatus.DRIVER_ASSIGNED,
            metadata={
                'driver_id': driver.id,
                'manual_override': True,
            },
        )

        payload = {'type': 'driver_assigned', 'driver_id': driver.id, 'manual_override': True}
        broadcast_to_order_group(order.id, payload)
        broadcast_to_admins({'event': 'driver_assigned', 'order_id': order.id, **payload})

        logger.info("Admin %s manually assigned driver %s to order %s", request.user.id, driver.id, order.id)
        return Response(AdminOrderDetailSerializer(order).data)


class AdminForceStatusView(BaseAppAdminAPIView):
    """
    POST /admin/orders/<order_id>/force-status/  { "status": "delivered", "reason": "..." }
    Full manual override of order status — always logged, use sparingly.
    """

    def post(self, request, order_id):
        serializer = ForceStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']
        reason = serializer.validated_data['reason']

        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({'detail': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

        old_status = order.status
        order.status = new_status
        order.save(update_fields=['status', 'last_modified_at'])

        OrderEvent.objects.create(
            order=order,
            event_type='admin_override',
            actor_type='admin',
            actor_id=request.user.id,
            old_status=old_status,
            new_status=new_status,
            metadata={'reason': reason},
        )

        payload = {'type': 'status_override', 'status': new_status, 'reason': reason}
        broadcast_to_order_group(order.id, payload)
        broadcast_to_admins({'event': 'status_override', 'order_id': order.id, **payload})

        logger.warning(
            "Admin %s forced order %s from %s to %s: %s",
            request.user.id, order.id, old_status, new_status, reason,
        )
        return Response(AdminOrderDetailSerializer(order).data)


class AdminCancelOrderView(BaseAppAdminAPIView):
    """POST /admin/orders/<order_id>/cancel/  { "reason": "..." } — routes through the normal cancel flow."""

    def post(self, request, order_id):
        serializer = CancelOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data['reason']

        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({'detail': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            # ACTORS likely doesn't have an ADMIN entry yet — using BRANCH as
            # the closest existing actor. Add ACTORS.ADMIN if you want this
            # distinguishable from a branch-initiated cancellation.
            cancel_order(order, ACTORS.BRANCH, reason)
        except Exception as exc:
            logger.exception("Admin cancel failed for order %s", order.id)
            return Response({'detail': f'Cancel failed: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

        order.refresh_from_db()
        # No separate admin broadcast here: cancel_order() is assumed to call
        # notify_order_cancelled() internally (matching the pattern in tasks.py),
        # which now calls broadcast_to_admins() itself. If cancel_order doesn't
        # go through notify_order_cancelled, add broadcast_to_admins(...) here.
        return Response(AdminOrderDetailSerializer(order).data)
