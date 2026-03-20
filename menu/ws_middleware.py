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
        token_type = query_params.get('token_type', [None])[0]
        
        def _normalize_token(raw):
            if not raw:
                return None, None
            stripped = raw.strip()
            lowered = stripped.lower()
            if lowered.startswith("bearer "):
                return stripped[7:].strip(), "bearer"
            if lowered.startswith("subbearer "):
                return stripped[10:].strip(), "sub"
            return stripped, None

        if token:
            token, detected_type = _normalize_token(token)
            if detected_type:
                token_type = detected_type
        else:
            headers = dict(scope.get('headers', []))
            auth_header = headers.get(b'authorization', b'').decode()
            if auth_header:
                token, token_type = _normalize_token(auth_header)
        
        # Store token in scope for consumer to use
        scope['token'] = token
        scope['token_type'] = token_type.lower() if token_type else None
        # Set a placeholder user (will be set in consumer)
        scope['user'] = AnonymousUser()
        
        return await super().__call__(scope, receive, send)

