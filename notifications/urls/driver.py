from rest_framework.routers import DefaultRouter

from notifications.views import DriverNotificationViewSet

router = DefaultRouter()
router.register("notifications", DriverNotificationViewSet, basename="driver-notifications")

urlpatterns = router.urls

