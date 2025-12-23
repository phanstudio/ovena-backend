"""
WebSocket authentication middleware
Place in: orders/ws_middleware.py
"""
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from django.conf import settings
import jwt
from urllib.parse import parse_qs


import asyncio



@database_sync_to_async
def get_user_from_token(token):
    """
    Decode JWT token and get user
    Adjust this based on your authentication system
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Decode JWT
        payload = jwt.decode(
            token,
            settings.SECRET_KEY, 
            algorithms=['HS256']
        )

        user_id = payload.get('user_id')
        if user_id:
            user = User.objects.select_related(
                'customer_profile',
                'driver_profile',
                'primaryagent__branch'
            ).get(id=user_id)
            return user
            
    except (jwt.ExpiredSignatureError, jwt.DecodeError, User.DoesNotExist):
        pass
    
    return AnonymousUser()


# class TokenAuthMiddleware(BaseMiddleware):
#     """
#     Custom middleware to authenticate WebSocket connections using JWT
#     Token can be passed via:
#     - Query parameter: ws://...?token=xxx
#     - Header (if supported by client)
#     """
    
#     async def __call__(self, scope, receive, send):
#         # Try to get token from query string
#         query_string = scope.get('query_string', b'').decode()
#         query_params = parse_qs(query_string)
#         token = query_params.get('token', [None])[0]
        
#         # If no token in query, try headers (some clients support this)
#         if not token:
#             headers = dict(scope.get('headers', []))
#             auth_header = headers.get(b'authorization', b'').decode()
#             if auth_header.startswith('Bearer '):
#                 token = auth_header[7:]
        
#         # Authenticate user
#         # # if token:
#         # #     scope['user'] = await get_user_from_token(token)
#         # # else:
#         # scope['user'] = AnonymousUser()

#         if token:
#             try:
#                 scope['user'] = await asyncio.wait_for(
#                     get_user_from_token(token), 
#                     timeout=3
#                 )
#             except asyncio.TimeoutError:
#                 print("Token authentication timed out")
#                 scope['user'] = AnonymousUser()
#         else:
#             scope['user'] = AnonymousUser()
        
#         return await super().__call__(scope, receive, send)





# # orders/ws_middleware.py
# import asyncio
# from functools import partial

# class TokenAuthMiddleware(BaseMiddleware):
#     async def __call__(self, scope, receive, send):
#         # Extract token
#         query_string = scope.get('query_string', b'').decode()
#         query_params = parse_qs(query_string)
#         token = query_params.get('token', [None])[0]
        
#         if not token:
#             headers = dict(scope.get('headers', []))
#             auth_header = headers.get(b'authorization', b'').decode()
#             if auth_header.startswith('Bearer '):
#                 token = auth_header[7:]
        
#         # Run authentication in thread pool to avoid blocking
#         if token:
#             loop = asyncio.get_event_loop()
#             try:
#                 # Run the synchronous auth function in a thread
#                 user = await loop.run_in_executor(
#                     None,  # Uses default ThreadPoolExecutor
#                     partial(self._sync_get_user_from_token, token)
#                 )
#                 scope['user'] = user
#             except Exception as e:
#                 print(f"Auth error: {e}")
#                 scope['user'] = AnonymousUser()
#         else:
#             scope['user'] = AnonymousUser()
        
#         return await super().__call__(scope, receive, send)
    
#     def _sync_get_user_from_token(self, token):
#         """Synchronous version for thread pool"""
#         try:
#             from django.contrib.auth import get_user_model
#             User = get_user_model()
            
#             # Minimal JWT decode
#             import jwt
#             payload = jwt.decode(
#                 token,
#                 settings.SECRET_KEY, 
#                 algorithms=['HS256']
#             )
            
#             user_id = payload.get('user_id')
#             if user_id:
#                 # LIGHTWEIGHT query - no select_related!
#                 user = User.objects.get(id=user_id)
                
#                 # Store in cache for 30 seconds to avoid repeated queries
#                 from django.core.cache import cache
#                 cache_key = f"ws_user_{user_id}"
#                 cache.set(cache_key, {
#                     'id': user.id,
#                     'email': user.email,
#                     # Don't store related objects
#                 }, 30)
                
#                 return user
#         except Exception:
#             pass
#         return AnonymousUser()
# orders/ws_middleware.py


# import jwt
# from urllib.parse import parse_qs
# from django.contrib.auth.models import AnonymousUser
# from django.conf import settings
# from channels.db import database_sync_to_async
# from channels.middleware import BaseMiddleware

# # from .async_user import AsyncSafeUser  # We'll define AsyncSafeUser in async_user.py

# # orders/async_user.py
# class AsyncSafeUser:
#     def __init__(self, user):
#         self._user = user
#         # Store the related profiles if they exist
#         self._driver_profile = None
#         self._primaryagent = None
#         self._customer_profile = None

#         # We assume the user object already has the related profiles loaded (via select_related)
#         if hasattr(user, 'driver_profile'):
#             self._driver_profile = user.driver_profile
#         if hasattr(user, 'primaryagent'):
#             self._primaryagent = user.primaryagent
#         if hasattr(user, 'customer_profile'):
#             self._customer_profile = user.customer_profile

#     @property
#     async def driver_profile(self):
#         return self._driver_profile

#     @property
#     async def primaryagent(self):
#         return self._primaryagent

#     @property
#     async def customer_profile(self):
#         return self._customer_profile

#     def __getattr__(self, name):
#         return getattr(self._user, name)

# class TokenAuthMiddleware(BaseMiddleware):
    # async def __call__(self, scope, receive, send):
    #     # Extract token
    #     query_string = scope.get('query_string', b'').decode()
    #     query_params = parse_qs(query_string)
    #     token = query_params.get('token', [None])[0]

    #     if not token:
    #         headers = dict(scope.get('headers', []))
    #         auth_header = headers.get(b'authorization', b'').decode()
    #         if auth_header.startswith('Bearer '):
    #             token = auth_header[7:]

    #     if token:
    #         try:
    #             payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
    #             user_id = payload.get('user_id')

    #             if user_id:
    #                 user = await self.get_user_sync(user_id)
    #                 if user.is_anonymous:
    #                     scope['user'] = user
    #                 else:
    #                     scope['user'] = AsyncSafeUser(user)
    #             else:
    #                 scope['user'] = AnonymousUser()
    #         except Exception as e:
    #             print(f"Auth error: {e}")
    #             scope['user'] = AnonymousUser()
    #     else:
    #         scope['user'] = AnonymousUser()

    #     return await super().__call__(scope, receive, send)

    # @database_sync_to_async
    # def get_user_sync(self, user_id):
    #     from django.contrib.auth import get_user_model
    #     User = get_user_model()
    #     try:
    #         return User.objects.select_related(
    #             'driver_profile',
    #             'primaryagent',
    #             'customer_profile'
    #         ).get(id=user_id)
    #     except User.DoesNotExist:
    #         return AnonymousUser()


# orders/ws_middleware.py
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from urllib.parse import parse_qs

class TokenAuthMiddleware(BaseMiddleware):
    """
    Simple middleware that just extracts the token
    Let consumers handle authentication
    """
    
    async def __call__(self, scope, receive, send):
        # Extract token
        query_string = scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        token = query_params.get('token', [None])[0]
        
        if not token:
            headers = dict(scope.get('headers', []))
            auth_header = headers.get(b'authorization', b'').decode()
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
        
        # Store token in scope for consumer to use
        scope['token'] = token
        # Set a placeholder user (will be set in consumer)
        scope['user'] = AnonymousUser()
        
        return await super().__call__(scope, receive, send)

