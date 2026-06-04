import json
import logging
from django.utils import timezone
from channels.db import database_sync_to_async
from menu.websocket_utils import (
    get_chat_group_name,
)
from menu.models import Order, ChatMessage
from accounts.models import User
from accounts.services.profiles import (
    PROFILE_CUSTOMER,
    PROFILE_DRIVER,
    PROFILE_BUSINESS_STAFF,
    get_profile,
)
from .base import (
    BaseConsumer, CLOSE_FORBIDDEN, CLOSE_UNAUTHENTICATED
)

logger = logging.getLogger(__name__)

class ChatConsumer(BaseConsumer):
    """
    WebSocket consumer for private messaging
    Handles 1-on-1 chats between order participants
    """
    
    async def connect_func(self):
        self.user = self.scope["user"]
        if not self.user or self.user.is_anonymous:
            await self.close(code=CLOSE_UNAUTHENTICATED)
            return
        
        self.order_id = self.scope["url_route"]["kwargs"]["order_id"]
        self.chat_group_name = get_chat_group_name(self.order_id)
        
        # Determine user type and ID
        self.user_type, self.user_id = await self.get_user_info()
        
        if not self.user_type:
            await self.close(code=CLOSE_FORBIDDEN)
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
        return True
    
    async def disconnect_func(self, close_code):
        if hasattr(self, "chat_group_name"):
            await self.channel_layer.group_discard(
                self.chat_group_name,
                self.channel_name
            )
    
    async def receive_func(self, message_type, data):
        """Receive chat message"""        
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

        if isinstance(user, User):
            customer = get_profile(user, PROFILE_CUSTOMER)
            if customer:
                return ("customer", customer.id)
            driver = get_profile(user, PROFILE_DRIVER)
            if driver:
                return ("driver", driver.id)
            branch = get_profile(user, PROFILE_BUSINESS_STAFF)
            if branch:
                return ("branch", branch.branch_id)
        
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
        except Exception:
            logger.exception("Failed to save chat message for order %s", self.order_id)
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
