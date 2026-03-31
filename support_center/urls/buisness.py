from support_center import views
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("support/tickets", views.BusinessSupportTicketViewSet, basename="driver-tickets")
urlpatterns = router.urls
