from support_center import views
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("support/tickets", views.CustomerSupportTicketViewSet, basename="customer-tickets")
urlpatterns = router.urls
