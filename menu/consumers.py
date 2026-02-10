from django.utils import timezone
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from menu.websocket_utils import (
    get_branch_group_name,
    get_driver_pool_group_name,
    get_order_group_name
)
from menu.models import Order, ChatMessage
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth.models import AnonymousUser
import json
from rest_framework_simplejwt.backends import TokenBackend
from django.conf import settings


class BaseConsumer(AsyncWebsocketConsumer):
    """Base consumer with authentication utilities"""
    
    async def authenticate_user(self, token):
        """Authenticate user from JWT token"""
        try:
            # Decode JWT, decode the sub token or the main token?
            decoded = AccessToken(token)
            # print(decoded)
            user_id = decoded['user_id']
            
            # Get user from database
            User = get_user_model()
            
            @database_sync_to_async
            def get_user():
                try:
                    # Use select_related to get profiles in one query
                    return User.objects.select_related(
                        'driver_profile',
                        'primaryagent',
                        'customer_profile'
                    ).get(id=user_id)
                except User.DoesNotExist:
                    return AnonymousUser()
            
            return await get_user()
        except Exception as e:
           


            backend = TokenBackend(
                algorithm=settings.SIMPLE_JWT.get("ALGORITHM", "HS256"),
                signing_key=settings.SECRET_KEY,
            )

            payload = backend.decode(token, verify=False)  # 🔥 THIS IS THE KEY

            now = int(timezone.now().timestamp())
            exp = payload.get("exp")

            print("exp:", exp)
            print("now:", now)
            print("seconds left:", exp - now)


            print(f"Authentication error: {e}")
            return AnonymousUser()
    
    @database_sync_to_async
    def check_is_driver(self, user):
        """Check if user is a driver"""
        return hasattr(user, 'driver_profile') and user.driver_profile is not None
    
    @database_sync_to_async
    def check_is_branch_staff(self, user): # add for the resturant staffs
        """Check if user is branch staff"""
        return hasattr(user, 'primaryagent') and user.primaryagent is not None
    
    @database_sync_to_async
    def check_is_customer(self, user):
        """Check if user is a customer"""
        return hasattr(user, 'customer_profile') and user.customer_profile is not None


class BranchConsumer(BaseConsumer): # for now it only works for primary staff not linked staffes will update soon
    """
    WebSocket consumer for branch staff
    Receives notifications about new orders and updates
    """
    
    async def connect(self):
        # Get token from scope
        token = self.scope.get('token')
        
        if not token:
            await self.close(code=4001)
            return
        
        # Authenticate user
        self.user = await self.authenticate_user(token)
        if not self.user or self.user.is_anonymous:
            await self.close(code=4001)
            return
        
        # Verify user is branch staff
        is_branch_staff = await self.check_is_branch_staff(self.user)
        if not is_branch_staff:
            await self.close(code=4003)
            return
        
        self.branch_id = self.scope['url_route']['kwargs']['branch_id']
        
        # Verify they belong to this branch
        if self.user.primaryagent.branch_id != int(self.branch_id):
            await self.close(code=4003)
            return
        
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
    
    async def disconnect(self, close_code):
        if hasattr(self, "branch_group_name"):
            await self.channel_layer.group_discard(
                self.branch_group_name,
                self.channel_name
            )

    
    async def receive(self, text_data):
        """Handle messages from branch staff"""
        data = json.loads(text_data)
        message_type = data.get('type')
        
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
    
    # @database_sync_to_async
    # def get_active_orders(self):
    #     """Get all active orders for this branch"""
    #     orders = Order.objects.filter(
    #         branch_id=self.branch_id,
    #         status__in=['pending', 'confirmed', 'payment_pending', 'preparing', 'ready']
    #     ).select_related('orderer__user').values(
    #         'id', 'order_number', 'status', 'created_at',
    #         'orderer__user__name'
    #     )
    #     return list(orders)

    @database_sync_to_async
    def get_active_orders(self):
        orders = Order.objects.filter(
            branch_id=self.branch_id,
            status__in=['pending','confirmed','payment_pending','preparing','ready']
        ).select_related('orderer__user').values(
            'id','order_number','status','created_at',
            'orderer__user__name'
        )

        serialized = []
        for order in orders:
            serialized.append({
                **order,
                'created_at': order['created_at'].isoformat() if order['created_at'] else None
            })

        return serialized

    
    async def join_active_order_groups(self):
        """Join WebSocket groups for all active orders"""
        order_ids = await self.get_active_order_ids()
        for order_id in order_ids:
            await self.channel_layer.group_add(
                get_order_group_name(order_id),
                self.channel_name
            )
    
    @database_sync_to_async
    def get_active_order_ids(self):
        """Get active order IDs for this branch"""
        return list(Order.objects.filter(
            branch_id=self.branch_id,
            status__in=['pending', 'confirmed', 'payment_pending', 'preparing', 'ready']
        ).values_list('id', flat=True))


class DriverOrdersConsumer(BaseConsumer):
    """
    WebSocket consumer for driver dashboard
    Shows available orders and order assignments
    """
    
    async def connect(self):
        # Get token from scope
        token = self.scope.get('token')
        
        if not token:
            await self.close(code=4001)
            return
        
        # Authenticate user
        self.user = await self.authenticate_user(token)
        if not self.user or self.user.is_anonymous:
            await self.close(code=4001)
            return
        
        # Verify user is a driver
        is_driver = await self.check_is_driver(self.user)
        if not is_driver:
            await self.close(code=4003)
            return
        
        self.driver_id = self.user.driver_profile.id
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

    async def disconnect(self, close_code):
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
    
    # async def disconnect(self, close_code):
    #     if hasattr(self, "driver_orders_group"):
    #         await self.channel_layer.group_discard(
    #             self.driver_orders_group,
    #             self.channel_name
    #         )

    #     if hasattr(self, "driver_id"):
    #         await self.channel_layer.group_discard(
    #             f"orders_{get_driver_pool_group_name()}",
    #             self.channel_name
    #         )

    async def receive(self, text_data):
        """Handle messages from driver"""
        data = json.loads(text_data)
        message_type = data.get('type')
        
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
            'type': 'notification',
            'data': event['data']
        }))
    
    async def driver_order_update(self, event):
        """Receive order updates"""
        await self.send(text_data=json.dumps({
            'type': 'order.update',
            'data': event['data']
        }))
    
    # @database_sync_to_async
    # def get_my_orders(self):
    #     """Get driver's current and recent orders"""
    #     orders = Order.objects.filter(
    #         driver_id=self.driver_id,
    #         status__in=['driver_assigned', 'picked_up', 'on_the_way']
    #     ).select_related('branch', 'orderer__user').values(
    #         'id', 'order_number', 'status', 'created_at',
    #         'branch__name', 'branch__location',
    #         'orderer__user__name'
    #     )
    #     return list(orders)

    @database_sync_to_async
    def get_my_orders(self):
        orders = Order.objects.filter(
            driver_id=self.driver_id,
            status__in=['driver_assigned', 'picked_up', 'on_the_way']
        ).select_related('branch', 'orderer__user').values(
            'id',
            'order_number',
            'status',
            'created_at',
            'branch__name',
            'branch__location',
            'orderer__user__name'
        )

        serialized = []
        for order in orders:
            serialized.append({
                'id': order['id'],
                'order_number': order['order_number'],
                'status': order['status'],
                'created_at': order['created_at'].isoformat()
                    if order['created_at'] else None,

                'branch': {
                    'name': order['branch__name'],
                    'location': {
                        'lat': order['branch__location'].y,
                        'lng': order['branch__location'].x,
                    } if order['branch__location'] else None
                },

                'customer_name': order['orderer__user__name'],
            })

        return serialized

class ChatConsumer(BaseConsumer):
    """
    WebSocket consumer for private messaging
    Handles 1-on-1 chats between order participants
    """
    
    async def connect(self):
        # Get token from scope
        token = self.scope.get('token')
        
        if not token:
            await self.close(code=4001)
            return
        
        # Authenticate user
        self.user = await self.authenticate_user(token)
        if not self.user or self.user.is_anonymous:
            await self.close(code=4001)
            return
        
        self.order_id = self.scope["url_route"]["kwargs"]["order_id"]
        self.chat_group_name = f"order_{self.order_id}_chat"
        
        # Determine user type and ID
        self.user_type, self.user_id = await self.get_user_info()
        
        if not self.user_type:
            await self.close(code=4003)
            return
        
        # Verify authorization for this order
        is_authorized = await self.check_order_authorization()
        if not is_authorized:
            await self.close(code=4003)
            return
        
        await self.accept()
        
        # Join chat room for this order
        await self.channel_layer.group_add(
            self.chat_group_name,
            self.channel_name
        )
        
        # Send recent messages
        recent_messages = await self.get_recent_messages()
        await self.send(text_data=json.dumps({
            'type': 'message_history',
            'data': recent_messages
        }))
    
    async def disconnect(self, close_code):
        if hasattr(self, "chat_group_name"):
            await self.channel_layer.group_discard(
                self.chat_group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """Receive chat message"""
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'send_message':
            recipient_type = data.get('recipient_type')
            message_text = data.get('message')
            
            if not recipient_type or not message_text:
                return
            
            # Save message
            message = await self.save_message(recipient_type, message_text)
            
            if message:
                # Broadcast to chat group
                await self.channel_layer.group_send(
                    self.chat_group_name,
                    {
                        'type': 'chat_message',
                        'data': {
                            'message_id': message['id'],
                            'sender_type': message['sender_type'],
                            'sender_id': message['sender_id'],
                            'recipient_type': message['recipient_type'],
                            'message': message['message'],
                            'timestamp': message['created_at']
                        }
                    }
                )
        
        elif message_type == 'mark_read':
            message_ids = data.get('message_ids', [])
            await self.mark_messages_read(message_ids)
    
    # Handler
    async def chat_message(self, event):
        """Send chat message to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'message',
            'data': event['data']
        }))
    
    @database_sync_to_async
    def get_user_info(self):
        """Determine user type and ID"""
        user = self.user
        
        if hasattr(user, 'customer_profile'):
            return ('customer', user.customer_profile.id)
        elif hasattr(user, 'driver_profile'):
            return ('driver', user.driver_profile.id)
        elif hasattr(user, 'primaryagent'):
            return ('branch', user.primaryagent.branch_id)
        
        return (None, None)
    
    @database_sync_to_async
    def check_order_authorization(self):
        """Check if user is part of this order"""
        try:
            order = Order.objects.only(
                "orderer_id", "driver_id", "branch_id"
            ).get(id=self.order_id)

            return (
                (self.user_type == "customer" and order.orderer_id == self.user_id)
                or (self.user_type == "driver" and order.driver_id == self.user_id)
                or (self.user_type == "branch" and order.branch_id == self.user_id)
            )
        except Order.DoesNotExist:
            return False
    
    @database_sync_to_async
    def save_message(self, recipient_type, message_text):
        """Save chat message to database"""
        try:
            # Get recipient ID based on order
            order = Order.objects.select_related('branch', 'driver', 'orderer').get(
                id=self.order_id
            )
            
            recipient_id = None
            if recipient_type == 'customer':
                recipient_id = order.orderer_id
            elif recipient_type == 'driver' and order.driver:
                recipient_id = order.driver_id
            elif recipient_type == 'branch':
                recipient_id = order.branch_id
            
            if not recipient_id:
                return None
            
            message = ChatMessage.objects.create(
                order_id=self.order_id,
                sender_type=self.user_type,
                sender_id=self.user_id,
                recipient_type=recipient_type,
                recipient_id=recipient_id,
                message=message_text
            )
            
            return {
                'id': message.id,
                'sender_type': message.sender_type,
                'sender_id': message.sender_id,
                'recipient_type': message.recipient_type,
                'message': message.message,
                'created_at': message.created_at.isoformat()
            }
        except Exception as e:
            print(f"Error saving message: {e}")
            return None
    
    @database_sync_to_async
    def get_recent_messages(self, limit=50):
        """Get recent chat messages for this order"""
        messages = ChatMessage.objects.filter(
            order_id=self.order_id
        ).order_by('-created_at')[:limit]

        return [
            {
                'id': m.id,
                'sender_type': m.sender_type,
                'sender_id': m.sender_id,
                'recipient_type': m.recipient_type,
                'message': m.message,
                'read_at': m.read_at.isoformat() if m.read_at else None,
                'created_at': m.created_at.isoformat()
            }
            for m in reversed(messages)
        ]
    
    @database_sync_to_async
    def mark_messages_read(self, message_ids):
        """Mark messages as read"""
        ChatMessage.objects.filter(
            id__in=message_ids,
            recipient_type=self.user_type,
            recipient_id=self.user_id,
            read_at__isnull=True
        ).update(read_at=timezone.now())


class OrderConsumer(BaseConsumer):
    """
    WebSocket consumer for order-specific updates
    Customers, drivers, and branch staff connect to track a specific order
    """
    
    async def connect(self):
        # Get token from scope
        token = self.scope.get('token')
        
        if not token:
            await self.close(code=4001)
            return
        
        # Authenticate user
        self.user = await self.authenticate_user(token)
        if not self.user or self.user.is_anonymous:
            await self.close(code=4001)
            return
        
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.order_group_name = get_order_group_name(self.order_id)
        
        # Verify user is authorized to view this order
        is_authorized = await self.check_authorization()
        
        if not is_authorized:
            await self.close(code=4003)
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
    
    async def disconnect(self, close_code):
        if hasattr(self, "order_group_name"):
            await self.channel_layer.group_discard(
                self.order_group_name,
                self.channel_name
            )

        
    async def receive(self, text_data):
        """Handle incoming messages from client"""
        data = json.loads(text_data)
        message_type = data.get('type')
        
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
    
    @database_sync_to_async
    def check_authorization(self):
        """Check if user is authorized to view this order"""
        try:
            order = Order.objects.select_related(
                'orderer__user', 
                'branch', 
                'driver__user'
            ).get(id=self.order_id)
            
            # Customer check
            if hasattr(self.user, 'customer_profile'):
                return order.orderer_id == self.user.customer_profile.id
            
            # Driver check
            if hasattr(self.user, 'driver_profile'):
                return order.driver_id == self.user.driver_profile.id
            
            # Branch staff check
            if hasattr(self.user, 'primaryagent'):
                return order.branch_id == self.user.primaryagent.branch_id
            
            return False
            
        except Order.DoesNotExist:
            return False
    
    @database_sync_to_async
    def get_order_data(self):
        """Get current order data"""
        try:
            order = Order.objects.select_related(
                'orderer__user',
                'branch',
                'driver__user'
            ).get(id=self.order_id)
            
            # Get driver location if assigned
            driver_location = None
            if order.driver:
                try:
                    from addresses.models import DriverLocation
                    loc:DriverLocation = order.driver.location
                    driver_location = {
                        'lat': loc.location.y,
                        'lng': loc.location.x,
                        'heading': loc.heading,
                        'last_updated': loc.last_updated.isoformat()
                    }
                except:
                    pass
            
            return {
                'order_id': order.id,
                'order_number': order.order_number,
                'status': order.status,
                'branch': {
                    'id': order.branch.id,
                    'name': order.branch.name,
                },
                'driver': {
                    'id': order.driver.id,
                    'name': order.driver.user.name,
                    'location': driver_location
                } if order.driver else None,
                'created_at': order.created_at.isoformat(),
                'estimated_delivery_time': order.estimated_delivery_time.isoformat() if order.estimated_delivery_time else None,
            }
        except Order.DoesNotExist:
            return None


class DriverLocationConsumer(BaseConsumer):
    """
    WebSocket consumer for driver location updates
    Drivers connect here to send GPS updates
    """
    
    async def connect(self):
        # Get token from scope
        token = self.scope.get('token')
        
        if not token:
            await self.close(code=4001)
            return
        
        # Authenticate user
        self.user = await self.authenticate_user(token)
        if not self.user or self.user.is_anonymous:
            await self.close(code=4001)
            return
        
        # Verify user is a driver
        is_driver = await self.check_is_driver(self.user)
        if not is_driver:
            await self.close(code=4003)
            return
        
        self.driver_id = self.user.driver_profile.id
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
    
    async def disconnect(self, close_code):
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

    async def receive(self, text_data):
        """Receive location updates from driver"""
        data = json.loads(text_data)
        message_type = data.get('type')

        if message_type == 'location_update':
            lat = data.get('lat')
            lng = data.get('lng')
            heading = data.get('heading', 0)
            speed = data.get('speed', 0)
            accuracy = data.get('accuracy', 0)
            
            if lat and lng:
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
            
            point = Point(float(lng), float(lat), srid=4326)
            
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
        except Exception as e:
            print(f"Error updating driver location: {e}")
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
        except Exception as e:
            print(f"Error setting driver status: {e}")
    
    @database_sync_to_async
    def set_driver_availability(self, is_available):
        """Update driver availability"""
        try:
            from menu.models import DriverProfile
            DriverProfile.objects.filter(id=self.driver_id).update(
                is_available=is_available
            )
            return True
        except Exception as e:
            print(f"Error setting driver availability: {e}")
            return False
    
    @database_sync_to_async
    def get_current_order_id(self):
        """Get driver's current order ID"""
        try:
            from menu.models import DriverProfile
            driver = DriverProfile.objects.get(id=self.driver_id)
            return driver.current_order_id
        except:
            return None
    
    async def broadcast_location_to_order(self, order_id, lat, lng, heading):
        """Broadcast driver location to order group"""
        from addresses.events import DRIVER_LOCATION_UPDATE
        
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


