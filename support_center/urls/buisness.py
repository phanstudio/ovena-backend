from support_center import views
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("support/tickets", views.BusinessSupportTicketViewSet, basename="business-tickets")
router.register("support/staff/tickets", views.BusinessStaffSupportTicketViewSet, basename="business-staff-tickets")
urlpatterns = router.urls
