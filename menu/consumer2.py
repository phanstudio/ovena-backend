# """
# WebSocket consumers - Part 2
# Add these to orders/consumers.py (after Part 1)
# """

# from django.utils import timezone
# from channels.generic.websocket import AsyncWebsocketConsumer
# from channels.db import database_sync_to_async
# from menu.websocket_utils import (
#     get_branch_group_name,
#     get_driver_pool_group_name
# )
# from menu.models import Order, ChatMessage
# import json

# class BranchConsumer(AsyncWebsocketConsumer):
#     """
#     WebSocket consumer for branch staff
#     Receives notifications about new orders and updates
#     """
    
#     async def connect(self):
#         self.user = self.scope['user']
        
#         # Verify user is branch staff
#         if not hasattr(self.user, 'primaryagent'):
#             await self.close(code=4003)
#             return
        
#         self.branch_id = self.scope['url_route']['kwargs']['branch_id']
        
#         # Verify they belong to this branch
#         if self.user.primaryagent.branch_id != int(self.branch_id):
#             await self.close(code=4003)
#             return
        
#         self.branch_group_name = get_branch_group_name(self.branch_id)
        
#         # Join branch group
#         await self.channel_layer.group_add(
#             self.branch_group_name,
#             self.channel_name
#         )
        
#         # Join active order groups for this branch
#         await self.join_active_order_groups()
        
#         await self.accept()
        
#         # Send current active orders
#         active_orders = await self.get_active_orders()
#         await self.send(text_data=json.dumps({
#             'type': 'active_orders',
#             'data': active_orders
#         }))
    
#     async def disconnect(self, close_code):
#         # Leave branch group
#         await self.channel_layer.group_discard(
#             self.branch_group_name,
#             self.channel_name
#         )
    
#     async def receive(self, text_data):
#         """Handle messages from branch staff"""
#         data = json.loads(text_data)
#         message_type = data.get('type')
        
#         if message_type == 'request_active_orders':
#             active_orders = await self.get_active_orders()
#             await self.send(text_data=json.dumps({
#                 'type': 'active_orders',
#                 'data': active_orders
#             }))
    
#     # Handler for branch notifications
#     async def branch_notification(self, event):
#         """Send notification to branch staff"""
#         await self.send(text_data=json.dumps({
#             'type': 'notification',
#             'data': event['data']
#         }))
    
#     # Handler for order updates
#     async def order_update(self, event):
#         """Forward order updates"""
#         await self.send(text_data=json.dumps({
#             'type': 'order.update',
#             'data': event['data']
#         }))
    
#     @database_sync_to_async
#     def get_active_orders(self):
#         """Get all active orders for this branch"""
#         orders = Order.objects.filter(
#             branch_id=self.branch_id,
#             status__in=['pending', 'confirmed', 'payment_pending', 'preparing', 'ready']
#         ).select_related('orderer__user').values(
#             'id', 'order_number', 'status', 'created_at',
#             'orderer__user__first_name', 'orderer__user__last_name'
#         )
#         return list(orders)
    
#     @database_sync_to_async
#     def join_active_order_groups(self):
#         """Join WebSocket groups for all active orders"""
#         active_order_ids = Order.objects.filter(
#             branch_id=self.branch_id,
#             status__in=['pending', 'confirmed', 'payment_pending', 'preparing', 'ready']
#         ).values_list('id', flat=True)
        
#         # Note: In production, you'd schedule this as a background task
#         # to avoid blocking. For now, we return the list to join them.
#         return list(active_order_ids)


# class DriverOrdersConsumer(AsyncWebsocketConsumer):
#     """
#     WebSocket consumer for driver dashboard
#     Shows available orders and order assignments
#     """
    
#     async def connect(self):
#         self.user = self.scope['user']
        
#         # Verify user is a driver
#         if not hasattr(self.user, 'driver_profile'):
#             await self.close(code=4003)
#             return
        
#         self.driver_id = self.user.driver_profile.id
#         self.driver_group_name = f"driver_{self.driver_id}"
        
#         # Join driver group
#         await self.channel_layer.group_add(
#             self.driver_group_name,
#             self.channel_name
#         )
        
#         # Join driver pool (for available orders broadcasts)
#         await self.channel_layer.group_add(
#             get_driver_pool_group_name(),
#             self.channel_name
#         )
        
#         await self.accept()
        
#         # Send current orders
#         my_orders = await self.get_my_orders()
#         await self.send(text_data=json.dumps({
#             'type': 'my_orders',
#             'data': my_orders
#         }))
    
#     async def disconnect(self, close_code):
#         await self.channel_layer.group_discard(
#             self.driver_group_name,
#             self.channel_name
#         )
#         await self.channel_layer.group_discard(
#             get_driver_pool_group_name(),
#             self.channel_name
#         )
    
#     async def receive(self, text_data):
#         """Handle messages from driver"""
#         data = json.loads(text_data)
#         message_type = data.get('type')
        
#         if message_type == 'request_orders':
#             my_orders = await self.get_my_orders()
#             await self.send(text_data=json.dumps({
#                 'type': 'my_orders',
#                 'data': my_orders
#             }))
    
#     # Handlers
#     async def driver_notification(self, event):
#         """Receive driver notifications (new order assignments)"""
#         await self.send(text_data=json.dumps({
#             'type': 'notification',
#             'data': event['data']
#         }))
    
#     async def order_update(self, event):
#         """Receive order updates"""
#         await self.send(text_data=json.dumps({
#             'type': 'order.update',
#             'data': event['data']
#         }))
    
#     @database_sync_to_async
#     def get_my_orders(self):
#         """Get driver's current and recent orders"""
#         orders = Order.objects.filter(
#             driver_id=self.driver_id,
#             status__in=['driver_assigned', 'picked_up', 'on_the_way']
#         ).select_related('branch', 'orderer__user').values(
#             'id', 'order_number', 'status', 'created_at',
#             'branch__name', 'branch__location',
#             'orderer__user__name'#, 'orderer__user__last_name'
#         )
#         return list(orders)


# class ChatConsumer(AsyncWebsocketConsumer):
#     """
#     WebSocket consumer for private messaging
#     Handles 1-on-1 chats between order participants
#     """
    
#     # async def connect(self):
#     #     print("CHAT CONNECT HIT", self.scope["url_route"]["kwargs"])
#     #     self.order_id = self.scope['url_route']['kwargs']['order_id']
#     #     self.user = self.scope['user']
        
#     #     # Determine user type and ID
#     #     self.user_type, self.user_id = await self.get_user_info()
        
#     #     if not self.user_type:
#     #         await self.close(code=4003)
#     #         return
        
#     #     # Verify authorization for this order
#     #     is_authorized = await self.check_order_authorization()
#     #     if not is_authorized:
#     #         await self.close(code=4003)
#     #         return
        
#     #     # Join chat room for this order
#     #     self.chat_group_name = f"order_{self.order_id}_chat"
#     #     await self.channel_layer.group_add(
#     #         self.chat_group_name,
#     #         self.channel_name
#     #     )
        
#     #     await self.accept()
        
#     #     # Send recent messages
#     #     recent_messages = await self.get_recent_messages()
#     #     await self.send(text_data=json.dumps({
#     #         'type': 'message_history',
#     #         'data': recent_messages
#     #     }))
    
#     # async def connect(self):
#     #     self.order_id = self.scope["url_route"]["kwargs"]["order_id"]
#     #     self.chat_group_name = f"order_{self.order_id}_chat"
#     #     self.user = self.scope.get("user")

#     #     print("CHAT CONNECT HIT", {"order_id": self.order_id})
#     #     # await self.accept()

#     #     if not self.user or not self.user.is_authenticated:
#     #         print(9999)
#     #         await self.close(code=4001)
#     #         return

#     #     self.user_type, self.user_id = await self.get_user_info()

#     #     if not self.user_type:
#     #         print(9999)
#     #         await self.close(code=4003)
#     #         return

#     #     is_authorized = await self.check_order_authorization()
#     #     if not is_authorized:
#     #         print(9999)
#     #         await self.close(code=4003)
#     #         return

#     #     await self.accept()
#     #     await self.channel_layer.group_add(
#     #         self.chat_group_name,
#     #         self.channel_name
#     #     )

#     #     print(99993)
#     #     # await self.accept()
#     #     print("CHAT CONNECT HIT USER", self.user)

#     #     recent_messages = await self.get_recent_messages()
#     #     await self.send(text_data=json.dumps({
#     #         'type': 'message_history',
#     #         'data': recent_messages
#     #     }))

#     # async def connect(self):
#     #     self.order_id = self.scope["url_route"]["kwargs"]["order_id"]
#     #     self.chat_group_name = f"order_{self.order_id}_chat"
#     #     self.user = self.scope.get("user")

#     #     print(vars(self.user))

#     #     print("CHAT CONNECT HIT", {"order_id": self.order_id, "user": self.user, "user_authenticated": self.user.is_authenticated})

#     #     # Check authentication BEFORE accepting
#     #     if not self.user or not self.user.is_authenticated:
#     #         print("User not authenticated, rejecting connection")
#     #         # Don't accept, just return
#     #         return


#     #     self.user_type, self.user_id = await self.get_user_info()


#     #     if not self.user_type:
#     #         print("Could not determine user type, rejecting connection")
#     #         return

#     #     is_authorized = await self.check_order_authorization()
#     #     if not is_authorized:
#     #         print("User not authorized for this order, rejecting connection")
#     #         return

#     #     # Only accept AFTER all checks pass
#     #     await self.accept()
#     #     print("CHAT CONNECT HIT USER", self.user)

#     #     # Join the group
#     #     await self.channel_layer.group_add(
#     #         self.chat_group_name,
#     #         self.channel_name
#     #     )

#     #     # Send recent messages
#     #     recent_messages = await self.get_recent_messages()
#     #     await self.send(text_data=json.dumps({
#     #         'type': 'message_history',
#     #         'data': recent_messages
#     #     }))

#     async def connect(self):
#         self.order_id = self.scope["url_route"]["kwargs"]["order_id"]
#         self.chat_group_name = f"order_{self.order_id}_chat"
#         self.user = self.scope.get("user")

#         print("CHAT CONNECT HIT", {
#             "order_id": self.order_id,
#             "user": self.user,
#             "authenticated": getattr(self.user, "is_authenticated", False)
#         })

#         # await self.accept()

#         # if not self.user or not self.user.is_authenticated:
#         #     await self.close(code=4001)
#         #     return

#         # self.user_type, self.user_id = await self.get_user_info()
#         self.user_type = "customer"
#         self.user_id = 2

#         if not self.user_type:
#             print("Could not determine user type")
#             await self.close(code=4003)
#             return
        
#         # await self.accept()

#         is_authorized = await self.check_order_authorization()
#         if not is_authorized:
#             await self.close(code=4003)
#             return

#         await self.accept()

#         await self.channel_layer.group_add(
#             self.chat_group_name,
#             self.channel_name
#         )

#         recent_messages = await self.get_recent_messages()
#         await self.send(text_data=json.dumps({
#             "type": "message_history",
#             "data": recent_messages
#         }))


#     # async def connect(self):
#     #     self.order_id = self.scope["url_route"]["kwargs"]["order_id"]
#     #     self.chat_group_name = f"order_{self.order_id}_chat"
#     #     self.user = self.scope.get("user")

#     #     print("CHAT CONNECT HIT", {"order_id": self.order_id, "user": self.user})

#     #     if not self.user or not self.user.is_authenticated:
#     #         print("CHAT: User not authenticated")
#     #         # Reject the connection
#     #         return

#     #     self.user_type, self.user_id = await self.get_user_info()
#     #     print(f"CHAT: user_type={self.user_type}, user_id={self.user_id}")

#     #     if not self.user_type:
#     #         print("CHAT: Could not determine user type")
#     #         return

#     #     is_authorized = await self.check_order_authorization()
#     #     print(f"CHAT: is_authorized={is_authorized}")

#     #     if not is_authorized:
#     #         print("CHAT: User not authorized for this order")
#     #         return

#     #     # All checks passed, now accept the connection
#     #     # await self.accept()
#     #     print("CHAT: Connection accepted")

#     #     await self.channel_layer.group_add(
#     #         self.chat_group_name,
#     #         self.channel_name
#     #     )
#     #     # await self.accept()

#     #     # recent_messages = await self.get_recent_messages()
#     #     # await self.send(text_data=json.dumps({
#     #     #     'type': 'message_history',
#     #     #     'data': recent_messages
#     #     # }))

#     #     try:
#     #         recent_messages = await self.get_recent_messages()
#     #         await self.send(text_data=json.dumps({
#     #             'type': 'message_history',
#     #             'data': recent_messages
#     #         }))
#     #     except Exception as e:
#     #         print(f"Error sending message history: {e}")
#     #         # We can close the connection or just log the error and continue
#     #         # If we close, the client will try to reconnect.
#     #         await self.close(code=4000)

#     # async def disconnect(self, close_code):
#     #     await self.channel_layer.group_discard(
#     #         self.chat_group_name,
#     #         self.channel_name
#     #     )

#     async def disconnect(self, close_code):
#         print(close_code)
#         if hasattr(self, "chat_group_name"):
#             await self.channel_layer.group_discard(
#                 self.chat_group_name,
#                 self.channel_name
#             )

    
#     async def receive(self, text_data):
#         """Receive chat message"""
#         data = json.loads(text_data)
#         message_type = data.get('type')
        
#         if message_type == 'send_message':
#             recipient_type = data.get('recipient_type')
#             message_text = data.get('message')
            
#             if not recipient_type or not message_text:
#                 return
            
#             # Save message
#             message = await self.save_message(recipient_type, message_text)
            
#             if message:
#                 # Broadcast to chat group
#                 await self.channel_layer.group_send(
#                     self.chat_group_name,
#                     {
#                         'type': 'chat_message',
#                         'data': {
#                             'message_id': message['id'],
#                             'sender_type': message['sender_type'],
#                             'sender_id': message['sender_id'],
#                             'recipient_type': message['recipient_type'],
#                             'message': message['message'],
#                             'timestamp': message['created_at']
#                         }
#                     }
#                 )
        
#         elif message_type == 'mark_read':
#             message_ids = data.get('message_ids', [])
#             await self.mark_messages_read(message_ids)
    
#     # Handler
#     async def chat_message(self, event):
#         """Send chat message to WebSocket"""
#         await self.send(text_data=json.dumps({
#             'type': 'message',
#             'data': event['data']
#         }))
    
#     @database_sync_to_async
#     def get_user_info(self):
#         """Determine user type and ID"""
#         user = self.user
        
#         if hasattr(user, 'customer_profile'):
#             return ('customer', user.customer_profile.id)
#         elif hasattr(user, 'driver_profile'):
#             return ('driver', user.driver_profile.id)
#         elif hasattr(user, 'primaryagent'):
#             return ('branch', user.primaryagent.branch_id)
        
#         return (None, None)
    
#     # @database_sync_to_async
#     # def check_order_authorization(self):
#     #     """Check if user is part of this order"""
#     #     try:
#     #         order = Order.objects.select_related('branch', 'driver', 'orderer').get(
#     #             id=self.order_id
#     #         )
            
#     #         if self.user_type == 'customer':
#     #             return order.orderer_id == self.user_id
#     #         elif self.user_type == 'driver':
#     #             return order.driver_id == self.user_id
#     #         elif self.user_type == 'branch':
#     #             return order.branch_id == self.user_id
            
#     #         return False
#     #     except Order.DoesNotExist:
#     #         return False
    
#     @database_sync_to_async
#     def check_order_authorization(self):
#         try:
#             order = Order.objects.only(
#                 "orderer_id", "driver_id", "branch_id"
#             ).get(id=self.order_id)

#             print(order.orderer_id)

#             return (
#                 (self.user_type == "customer" and order.orderer_id == self.user_id)
#                 or (self.user_type == "driver" and order.driver_id == self.user_id)
#                 or (self.user_type == "branch" and order.branch_id == self.user_id)
#             )
#         except Order.DoesNotExist:
#             return False

#     @database_sync_to_async
#     def save_message(self, recipient_type, message_text):
#         """Save chat message to database"""
#         try:
#             # Get recipient ID based on order
#             order = Order.objects.select_related('branch', 'driver', 'orderer').get(
#                 id=self.order_id
#             )
            
#             recipient_id = None
#             if recipient_type == 'customer':
#                 recipient_id = order.orderer_id
#             elif recipient_type == 'driver' and order.driver:
#                 recipient_id = order.driver_id
#             elif recipient_type == 'branch':
#                 recipient_id = order.branch_id
            
#             if not recipient_id:
#                 return None
            
#             message = ChatMessage.objects.create(
#                 order_id=self.order_id,
#                 sender_type=self.user_type,
#                 sender_id=self.user_id,
#                 recipient_type=recipient_type,
#                 recipient_id=recipient_id,
#                 message=message_text
#             )
            
#             return {
#                 'id': message.id,
#                 'sender_type': message.sender_type,
#                 'sender_id': message.sender_id,
#                 'recipient_type': message.recipient_type,
#                 'message': message.message,
#                 'created_at': message.created_at.isoformat()
#             }
#         except Exception as e:
#             print(f"Error saving message: {e}")
#             return None
    
#     @database_sync_to_async
#     def get_recent_messages(self, limit=50):
#         """Get recent chat messages for this order"""
#         messages = ChatMessage.objects.filter(
#             order_id=self.order_id
#         ).order_by('-created_at')[:limit]

#         return [
#             {
#                 'id': m.id,
#                 'sender_type': m.sender_type,
#                 'sender_id': m.sender_id,
#                 'recipient_type': m.recipient_type,
#                 'message': m.message,
#                 'read_at': m.read_at.isoformat() if m.read_at else None,
#                 'created_at': m.created_at.isoformat()
#             }
#             for m in reversed(messages)
#         ]
    
#     @database_sync_to_async
#     def mark_messages_read(self, message_ids):
#         """Mark messages as read"""
#         ChatMessage.objects.filter(
#             id__in=message_ids,
#             recipient_type=self.user_type,
#             recipient_id=self.user_id,
#             read_at__isnull=True
#         ).update(read_at=timezone.now())


