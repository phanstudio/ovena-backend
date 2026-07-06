import json
import logging

from django.utils import timezone
from channels.db import database_sync_to_async
from menu.websocket_utils import (
    get_driver_pool_group_name,
    get_order_group_name,
)
from menu.models import Order
from django.db.models import Subquery
from accounts.models import DriverProfile
from .base import (
    BaseConsumer, CLOSE_FORBIDDEN, CLOSE_UNAUTHENTICATED
)

logger = logging.getLogger(__name__)

class DriverOrdersConsumer(BaseConsumer):
    """
    WebSocket consumer for driver dashboard
    Shows available orders and order assignments
    """
    
    async def connect_func(self):
        self.user = self.scope["user"]
        if not self.user or self.user.is_anonymous:
            await self.close(code=CLOSE_UNAUTHENTICATED)
            return
        
        # Verify user is a driver
        driver_profile:DriverProfile = await self.get_driver_profile(self.user)
        if not driver_profile:
            await self.close(code=CLOSE_FORBIDDEN)
            return

        self.driver_id = driver_profile.id
        self.driver_orders_group = f"driver_orders_{self.driver_id}"
        self.driver_notification_group = f"driver_{self.driver_id}"  # NEW
        
        # Join driver group
        await self.channel_layer.group_add(
            self.driver_orders_group,
            self.channel_name
        )

        # Join driver notification group (for task notifications)
        await self.channel_layer.group_add(
            self.driver_notification_group,  # NEW
            self.channel_name
        )

        
        # Join driver pool (for available orders broadcasts)
        await self.channel_layer.group_add(
            f"orders_{get_driver_pool_group_name()}",
            self.channel_name
        )
        
        await self.accept()
        
        # Send current orders
        my_orders = await self.get_my_orders()
        await self.send(text_data=json.dumps({
            'type': 'my_orders',
            'data': my_orders
        }))
        return True

    async def disconnect_func(self, close_code):
        if hasattr(self, "driver_orders_group"):
            await self.channel_layer.group_discard(
                self.driver_orders_group,
                self.channel_name
            )
        
        if hasattr(self, "driver_notification_group"):  # NEW
            await self.channel_layer.group_discard(
                self.driver_notification_group,
                self.channel_name
            )
        
        if hasattr(self, "driver_id"):
            await self.channel_layer.group_discard(
                f"orders_{get_driver_pool_group_name()}",
                self.channel_name
            )
    
    # Add handler for driver_notification type
    async def driver_notification(self, event):  # NEW
        """Receive driver notifications from tasks"""
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'data': event['data']
        }))
    
    async def receive_func(self, message_type, data):
        """Handle messages from driver"""
        if message_type == 'request_orders':
            my_orders = await self.get_my_orders()
            await self.send(text_data=json.dumps({
                'type': 'my_orders',
                'data': my_orders
            }))
    
    # Handlers
    async def driver_orders_notification(self, event):
        """Receive driver notifications (new order assignments)"""
        await self.send(text_data=json.dumps({
            'type': 'order_message',
            'data': event['data']
        }))
    
    async def driver_order_update(self, event):
        """Receive order updates"""
        await self.send(text_data=json.dumps({
            'type': 'order.update',
            'data': event['data']
        }))

    @database_sync_to_async
    def get_my_orders(self):
        last_event = self.last_order_event_subquery()

        orders = Order.objects.filter(
            driver_id=self.driver_id,
            status__in=['driver_assigned', 'picked_up', 'on_the_way']
        ).select_related('branch','orderer__user').annotate(
            last_event_type=Subquery(last_event.values('event_type')[:1]),
            last_event_time=Subquery(last_event.values('timestamp')[:1]),
            last_event_metadata=Subquery(last_event.values('metadata')[:1]),
        ).values(
            'id','order_number','status',
            'created_at','branch__name',
            'branch__location','orderer__name',
            'last_event_type','last_event_time', 'last_event_metadata',
            'orderer__user__phone_number'
        )

        serialized = []
        for order in orders:
            serialized.append({
                'id': order['id'],
                'order_number': order['order_number'],
                'status': order['status'],
                'created_at': order['created_at'].isoformat() if order['created_at'] else None,

                'last_event': {
                    'type': order['last_event_type'],
                    'timestamp': order['last_event_time'].isoformat() if order['last_event_time'] else None,
                    'metadata': order['last_event_metadata']
                },

                'branch': {
                    'name': order['branch__name'],
                    'location': {
                        'lat': order['branch__location'].y,
                        'lng': order['branch__location'].x,
                    } if order['branch__location'] else None
                },
                "delivery_type": "Meet at door",
                'customer_name': order['orderer__name'],
                'customer_phone_number': order['orderer__phone_number'],
            })

        logger.info(f"{len(serialized)}")
        print(len(serialized))
        DriverProfile.objects.filter(id=self.driver_id).update(
            is_available = False if len(serialized) else True
        )
        return serialized

class DriverLocationConsumer(BaseConsumer):
    """
    WebSocket consumer for driver location updates
    Drivers connect here to send GPS updates
    """
    
    async def connect_func(self):
        self.user = self.scope["user"]
        if not self.user or self.user.is_anonymous:
            await self.close(code=CLOSE_UNAUTHENTICATED)
            return
        
        # Verify user is a driver
        driver_profile = await self.get_driver_profile(self.user)
        if not driver_profile:
            await self.close(code=CLOSE_FORBIDDEN)
            return
        
        self.driver_id = driver_profile.id
        self.driver_location_group = f"driver_location_{self.driver_id}"
        
        # Join driver's personal group (for notifications)
        await self.channel_layer.group_add(
            self.driver_location_group,
            self.channel_name
        )
        
        # Join global driver pool
        await self.channel_layer.group_add(
            f"location_{get_driver_pool_group_name()}",
            self.channel_name
        )
        
        await self.accept()
        
        # Mark driver as online
        await self.set_driver_status(is_online=True)
        return True
    
    async def disconnect_func(self, close_code):
        if hasattr(self, "driver_location_group"):
            await self.channel_layer.group_discard(
                self.driver_location_group,
                self.channel_name
            )

        await self.channel_layer.group_discard(
            f"location_{get_driver_pool_group_name()}",
            self.channel_name
        )

        if hasattr(self, "driver_id"):
            await self.set_driver_status(is_online=False)

    async def receive_func(self, message_type, data):
        """Receive location updates from driver"""
        if message_type == 'location_update':
            lat = data.get('lat')
            lng = data.get('lng')
            heading = data.get('heading', 0)
            speed = data.get('speed', 0)
            accuracy = data.get('accuracy', 0)
            
            if lat is not None and lng is not None:
                await self.update_driver_location(lat, lng, heading, speed, accuracy)
                
                # If driver is on an active order, broadcast to that order group
                order_id = await self.get_current_order_id()
                if order_id:
                    await self.broadcast_location_to_order(order_id, lat, lng, heading)
        
        elif message_type == 'status_change':
            is_available = data.get('is_available', False)
            await self.set_driver_availability(is_available)
    
    # Handler for driver notifications
    async def driver_location_notification(self, event):
        """Send notification to driver"""
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'data': event['data']
        }))
    
    @database_sync_to_async
    def update_driver_location(self, lat, lng, heading, speed, accuracy):
        """Update driver location in database"""
        try:
            from django.contrib.gis.geos import Point
            from addresses.models import DriverLocation
            
            try:
                lng_float = float(lng)
                lat_float = float(lat)
            except (TypeError, ValueError) as exc:
                logger.warning("Invalid location data from driver %s: %s", self.driver_id, exc)
                return False
            point = Point(lng_float, lat_float, srid=4326)
            
            location, created = DriverLocation.objects.update_or_create(
                driver_id=self.driver_id,
                defaults={
                    'location': point,
                    'heading': heading,
                    'speed': speed,
                    'accuracy': accuracy,
                    'is_online': True,
                    'last_updated': timezone.now()
                }
            )
            return True
        except Exception:
            logger.exception("Failed to update location for driver %s", self.driver_id)
            return False
    
    @database_sync_to_async
    def set_driver_status(self, is_online):
        """Update driver online status"""
        try:
            from menu.models import DriverProfile
            from addresses.models import DriverLocation
            
            DriverProfile.objects.filter(id=self.driver_id).update(
                is_online=is_online
            )
            DriverLocation.objects.filter(driver_id=self.driver_id).update(
                is_online=is_online
            )
        except Exception:
            logger.exception("Failed to update online status for driver %s", self.driver_id)
    
    @database_sync_to_async
    def set_driver_availability(self, is_available):
        """Update driver availability"""
        try:
            from menu.models import DriverProfile
            DriverProfile.objects.filter(id=self.driver_id).update(
                is_available=is_available
            )
            return True
        except Exception:
            logger.exception("Failed to update availability for driver %s", self.driver_id)
            return False
    
    @database_sync_to_async
    def get_current_order_id(self):
        """Get driver's current order ID"""
        try:
            from menu.models import DriverProfile
            driver = DriverProfile.objects.get(id=self.driver_id)
            return driver.current_order_id
        except Exception:
            return None
    
    async def broadcast_location_to_order(self, order_id, lat, lng, heading):
        """Broadcast driver location to order group"""
        from menu.events import DRIVER_LOCATION_UPDATE
        
        await self.channel_layer.group_send(
            get_order_group_name(order_id),
            {
                'type': 'order_update',
                'data': {
                    'type': DRIVER_LOCATION_UPDATE,
                    'driver_id': self.driver_id,
                    'location': {
                        'lat': lat,
                        'lng': lng,
                        'heading': heading
                    },
                    'timestamp': timezone.now().isoformat()
                }
            }
        )
