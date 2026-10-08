from rest_framework.routers import DefaultRouter
from notifications.views import (
    CustomerNotificationViewSet, CustomerRegisterDeviceTokenView, CustomerUnRegisterDeviceTokenView
)
from django.urls import path

router = DefaultRouter()
router.register("notifications", CustomerNotificationViewSet, basename="customer-notifications")

urlpatterns = [
    *router.urls,
    path(
        "notifications/register-device/",
        CustomerRegisterDeviceTokenView.as_view(),
        name="customer-register-device",
    ),
    path(
        "notifications/unregister-device/",
        CustomerUnRegisterDeviceTokenView.as_view(),
        name="customer-unregister-device",
    ),
]
