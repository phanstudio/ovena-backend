from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from urllib.parse import parse_qs
from authflow.authentication import CustomJWtAuth
from rest_framework_simplejwt.tokens import AccessToken


@database_sync_to_async
def get_user_from_token(token):
    try:
        access = AccessToken(token)
        auth = CustomJWtAuth()
        return auth.get_user(access)
    except Exception:
        return AnonymousUser()

# (BaseMiddleware)
class TokenAuthMiddleware:

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):

        query = parse_qs(scope["query_string"].decode())
        token = query.get("token", [None])[0]
        print(token)

        if token:
            scope["user"] = await get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()

        return await self.app(scope, receive, send)


# # ws_middleware.py
# from functools import lru_cache
# import asyncio
# from urllib.parse import parse_qs
# from django.contrib.auth.models import AnonymousUser
# from rest_framework_simplejwt.tokens import AccessToken
# from channels.db import database_sync_to_async
# from authflow.authentication import CustomJWtAuth

# # In-memory token cache to avoid repeated DB hits for the same token
# _token_cache: dict[str, any] = {}
# _token_cache_lock = asyncio.Lock()

# @database_sync_to_async
# def _fetch_user_from_token(token):
#     try:
#         access = AccessToken(token)
#         auth = CustomJWtAuth()
#         return auth.get_user(access)
#     except Exception:
#         return AnonymousUser()


# async def get_user_from_token(token: str):
#     """
#     Cached token resolution — multiple simultaneous connections
#     with the same token only hit the DB once.
#     """
#     async with _token_cache_lock:
#         if token in _token_cache:
#             return _token_cache[token]

#     # DB fetch outside the lock so other tokens aren't blocked
#     user = await _fetch_user_from_token(token)

#     async with _token_cache_lock:
#         _token_cache[token] = user  # last-write-wins, acceptable here

#     return user


# class TokenAuthMiddleware:

#     def __init__(self, app):
#         self.app = app

#     async def __call__(self, scope, receive, send):
#         if scope["type"] != "websocket":
#             return await self.app(scope, receive, send)

#         query = parse_qs(scope["query_string"].decode())
#         token = query.get("token", [None])[0]

#         if token:
#             scope["user"] = await get_user_from_token(token)
#         else:
#             scope["user"] = AnonymousUser()

#         return await self.app(scope, receive, send)

