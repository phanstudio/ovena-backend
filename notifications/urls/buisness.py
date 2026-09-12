from rest_framework.routers import DefaultRouter
from notifications.views import BuisnessNotificationViewSet, BusinessRegisterDeviceTokenView
from django.urls import path

router = DefaultRouter()
router.register("notifications", BuisnessNotificationViewSet, basename="buisness-notifications")

urlpatterns = [
    *router.urls,
    path(
        "notifications/register-device/",
        BusinessRegisterDeviceTokenView.as_view(),
        name="driver-register-device",
    ),
]
