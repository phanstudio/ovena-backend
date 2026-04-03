from rest_framework.routers import DefaultRouter
from notifications.views import BuisnessNotificationViewSet

router = DefaultRouter()
router.register("notifications", BuisnessNotificationViewSet, basename="buisness-notifications")

urlpatterns = router.urls