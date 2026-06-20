import json
import logging
from channels.db import database_sync_to_async
from menu.websocket_utils import (
    get_branch_group_name,
    get_order_group_name,
)
from menu.models import Order
from django.db.models import Subquery
from .base import (
    BaseConsumer, CLOSE_FORBIDDEN, CLOSE_UNAUTHENTICATED
)

logger = logging.getLogger(__name__)

class BranchConsumer(BaseConsumer):
    """
    WebSocket consumer for branch staff
    Receives notifications about new orders and updates
    """
    
    async def connect_func(self):
        self.user = self.scope["user"]
        if not self.user or self.user.is_anonymous:
            await self.close(code=CLOSE_UNAUTHENTICATED)
            return

        # Verify user is branch staff
        is_branch_staff = await self.check_is_branch_staff(self.user)
        if not is_branch_staff:
            await self.close(code=CLOSE_FORBIDDEN)
            return

        branch_staff = await self.get_branch_staff(self.user)
        self.branch_id = branch_staff.branch_id
        
        self.branch_group_name = get_branch_group_name(self.branch_id)
        
        # Join branch group
        await self.channel_layer.group_add(
            self.branch_group_name,
            self.channel_name
        )
        
        # Join active order groups for this branch
        await self.join_active_order_groups()
        await self.accept()
        
        # Send current active orders
        active_orders = await self.get_active_orders()
        await self.send(text_data=json.dumps({
            'type': 'active_orders',
            'data': active_orders
        }))
        return True
    
    async def disconnect_func(self, close_code):
        if hasattr(self, "branch_group_name"):
            await self.channel_layer.group_discard(
                self.branch_group_name,
                self.channel_name
            )

    async def receive_func(self, message_type, data):
        """Handle messages from branch staff"""
        if message_type == 'request_active_orders':
            active_orders = await self.get_active_orders()
            await self.send(text_data=json.dumps({
                'type': 'active_orders',
                'data': active_orders
            }))
    
    # Handler for branch notifications
    async def branch_notification(self, event):
        """Send notification to branch staff"""
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'data': event['data']
        }))
    
    # Handler for order updates
    async def order_update(self, event):
        """Forward order updates"""
        await self.send(text_data=json.dumps({
            'type': 'order.update',
            'data': event['data']
        }))
    
    @database_sync_to_async
    def get_active_orders(self):
        last_event = self.last_order_event_subquery()

        orders = Order.objects.filter(
            branch_id=self.branch_id,
            status__in=['pending', 'confirmed', 'payment_pending', 'preparing', 'ready']
        ).select_related('orderer').annotate(
            last_event_type=Subquery(last_event.values('event_type')[:1]),
            last_event_time=Subquery(last_event.values('timestamp')[:1]),
            last_event_metadata=Subquery(last_event.values('metadata')[:1]),
            
        ).values(
            'id','order_number','status','created_at',
            'orderer__name','last_event_type','last_event_time', 
            'last_event_metadata', 'subtotal'
        )

        return [
            {
                **order,
                'created_at': order['created_at'].isoformat() if order['created_at'] else None,
                'last_event_time': order['last_event_time'].isoformat() if order['last_event_time'] else None,
                'amount': order['subtotal']
            }
            for order in orders
        ]

    
    async def join_active_order_groups(self):
        """Join WebSocket groups for all active orders"""
        order_ids = await self.get_active_order_ids()
        for order_id in order_ids:
            await self.channel_layer.group_add(
                get_order_group_name(order_id),
                self.channel_name
            )
    
    @database_sync_to_async
    def get_active_order_ids(self): # doing the samething
        """Get active order IDs for this branch"""
        return list(Order.objects.filter(
            branch_id=self.branch_id,
            status__in=['pending', 'confirmed', 'payment_pending', 'preparing', 'ready']
        ).values_list('id', flat=True))
