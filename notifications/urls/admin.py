from rest_framework.routers import DefaultRouter
from notifications.views import (
    AdminNotificationViewSet, AdminRegisterDeviceTokenView, AdminUnRegisterDeviceTokenView
)
from django.urls import path

router = DefaultRouter()
router.register("notifications", AdminNotificationViewSet, basename="admin-notifications")

urlpatterns = [
    *router.urls,
    path(
        "notifications/register-device/",
        AdminRegisterDeviceTokenView.as_view(),
        name="admin-register-device",
    ),
    path(
        "notifications/unregister-device/",
        AdminUnRegisterDeviceTokenView.as_view(),
        name="admin-unregister-device",
    ),
]
