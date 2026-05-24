from rest_framework.routers import DefaultRouter
from notifications.views import CustomerNotificationViewSet

router = DefaultRouter()
router.register("notifications", CustomerNotificationViewSet, basename="customer-notifications")

urlpatterns = router.urls