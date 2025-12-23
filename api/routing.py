"""
WebSocket URL routing
Place in: api/routing.py
"""
from django.urls import re_path
from menu import consumers

websocket_urlpatterns = [
    # Order updates (customer, branch, driver)
    re_path(r'ws/orders/(?P<order_id>\d+)/$', consumers.OrderConsumer.as_asgi()),
    
    # Driver location updates
    re_path(r'ws/driver/location/$', consumers.DriverLocationConsumer.as_asgi()),
    
    # Branch dashboard (all orders for a branch)
    re_path(r'ws/branch/(?P<branch_id>\d+)/$', consumers.BranchConsumer.as_asgi()),
    
    # Driver dashboard (available orders + assignments)
    re_path(r'ws/driver/orders/$', consumers.DriverOrdersConsumer.as_asgi()),
    
    # Private chat
    re_path(r'ws/orders/(?P<order_id>\d+)/chat/$', consumers.ChatConsumer.as_asgi()),
]