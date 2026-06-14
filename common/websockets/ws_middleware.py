from channels.db import database_sync_to_async
# from channels.middleware import BaseMiddleware
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

        if token:
            scope["user"] = await get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()

        return await self.app(scope, receive, send)
