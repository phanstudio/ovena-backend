from django.urls import path, include
from support_center import views
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("support/tickets", views.AppAdminSupportTicketViewSet, basename="app-admin-tickets")
urlpatterns = router.urls
