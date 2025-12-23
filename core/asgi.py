# myproject/asgi.py

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
import api.routing
from menu.ws_middleware import TokenAuthMiddleware

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    # "websocket": URLRouter(api.routing.websocket_urlpatterns),
    "websocket": AllowedHostsOriginValidator(
        TokenAuthMiddleware(
            URLRouter(api.routing.websocket_urlpatterns)
        )
    ),
})
