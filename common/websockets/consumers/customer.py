import json
import logging
from channels.db import database_sync_to_async
from menu.websocket_utils import (
    get_order_group_name,
)
from menu.models import Order
from accounts.models import User
from django.db.models import Subquery
from .base import (
    BaseConsumer, CLOSE_FORBIDDEN, CLOSE_UNAUTHENTICATED
)
from image.utils import get_image
from common.phone.utils import get_phone_number

logger = logging.getLogger(__name__)

# {
# # itemCount: 4,
# # amount: "₦4,100.00",
# }

class OrderConsumer(BaseConsumer):
    """
    WebSocket consumer for order-specific updates
    Customers, drivers, and branch staff connect to track a specific order
    """
    
    async def connect_func(self):
        self.user = self.scope["user"]
        if not self.user or self.user.is_anonymous:
            await self.close(code=CLOSE_UNAUTHENTICATED)
            return
        
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.order_group_name = get_order_group_name(self.order_id)
        
        # Verify user is authorized to view this order
        is_authorized = await self.check_authorization()
        
        if not is_authorized:
            await self.close(code=CLOSE_FORBIDDEN)
            return
        
        # Only accept after authorization check
        await self.accept()
        
        # Join order group
        await self.channel_layer.group_add(
            self.order_group_name,
            self.channel_name
        )
        
        # Send current order status
        order_data = await self.get_order_data()
        await self.send(text_data=json.dumps({
            'type': 'order.status',
            'data': order_data
        }))
        return True
    
    async def disconnect_func(self, close_code):
        if hasattr(self, "order_group_name"):
            await self.channel_layer.group_discard(
                self.order_group_name,
                self.channel_name
            )
 
    async def receive_func(self, message_type, data):
        """Handle incoming messages from client"""
        # Handle different message types if needed
        # (Most updates are server-initiated, but client can request status)
        if message_type == 'request_status':
            order_data = await self.get_order_data()
            await self.send(text_data=json.dumps({
                'type': 'order.status',
                'data': order_data
            }))
    
    # Handlers for group messages
    async def order_update(self, event):
        """Send order update to WebSocket client"""
        await self.send(text_data=json.dumps({
            'type': 'order.update',
            'data': event['data']
        }))
    
    # @database_sync_to_async
    async def check_authorization(self):
        """Check if user is authorized to view this order"""
        try:
            order = await self.get_order()
            
            if isinstance(self.user, User):
                customer = await self.get_customer_profile(self.user)
                if customer:
                    return order.orderer_id == customer.id

                driver = await self.get_driver_profile(self.user)
                if driver:
                    return order.driver_id == driver.id

                branch_staff = await self.get_branch_staff(self.user)
                if branch_staff:
                    return order.branch_id == branch_staff.branch_id
            
            return False
            
        except Order.DoesNotExist:
            return False
    
    @database_sync_to_async
    def get_order(self):
        return Order.objects.select_related(
            'orderer__user', 
            'branch', 
            'driver__user'
        ).get(id=self.order_id)
    
    @database_sync_to_async
    def get_order_data(self):
        try:
            last_event = self.last_order_event_subquery()

            order = Order.objects.select_related(
                'orderer__user','branch','driver__user', 'branch__business'
            ).filter(id=self.order_id).annotate(
                last_event_type=Subquery(last_event.values('event_type')[:1]),
                last_event_time=Subquery(last_event.values('timestamp')[:1]),
                last_event_metadata=Subquery(last_event.values('metadata')[:1]),
            ).first()

            if not order:
                return None

            driver_location = None
            if order.driver:
                try:
                    from addresses.models import DriverLocation
                    loc = order.driver.location
                    driver_location = {
                        'lat': loc.location.y,
                        'lng': loc.location.x,
                        'heading': loc.heading,
                        'last_updated': loc.last_updated.isoformat()
                    }
                except:
                    pass

            business_image = order.branch.business.business_image

            return {
                'order_id': order.id,
                'order_number': order.order_number,
                'status': order.status,

                'last_event': {
                    'type': order.last_event_type,
                    'timestamp': order.last_event_time.isoformat() if order.last_event_time else None,
                    'metadata': order.last_event_metadata,
                },

                'branch': {
                    'id': order.branch.id,
                    'name': order.branch.name,
                    'business_image': get_image(business_image)
                },

                'driver': {
                    'id': order.driver.id,
                    'name': order.driver.full_name,
                    'location': driver_location,
                    'phone_number': get_phone_number(order.driver.user.phone_number)
                } if order.driver else None,

                'created_at': order.created_at.isoformat(),
                'estimated_delivery_time': order.estimated_delivery_time.isoformat()
                    if order.estimated_delivery_time else None,
            }

        except Order.DoesNotExist:
            return None
