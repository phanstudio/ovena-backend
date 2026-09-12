from rest_framework.routers import DefaultRouter
from django.urls import path

from notifications.views import DriverNotificationViewSet, DriverRegisterDeviceTokenView

router = DefaultRouter()
router.register("notifications", DriverNotificationViewSet, basename="driver-notifications")

urlpatterns = [
    *router.urls,
    path(
        "notifications/register-device/",
        DriverRegisterDeviceTokenView.as_view(),
        name="driver-register-device",
    ),
]