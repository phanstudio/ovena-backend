from rest_framework.routers import DefaultRouter
from notifications.views import (
    BuisnessNotificationViewSet, BusinessRegisterDeviceTokenView, BusinessUnRegisterDeviceTokenView
)
from django.urls import path

router = DefaultRouter()
router.register("notifications", BuisnessNotificationViewSet, basename="buisness-notifications")

urlpatterns = [
    *router.urls,
    path(
        "notifications/register-device/",
        BusinessRegisterDeviceTokenView.as_view(),
        name="business-register-device",
    ),
    path(
        "notifications/unregister-device/",
        BusinessUnRegisterDeviceTokenView.as_view(),
        name="business-unregister-device",
    ),
]
