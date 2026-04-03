from rest_framework.routers import DefaultRouter
from notifications.views import NotificationViewSet

router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notifications")

urlpatterns = router.urls