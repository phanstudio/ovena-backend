from django.urls import path, include
from support_center import views
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("help/tickets", views.DriverSupportTicketViewSet, basename="driver-tickets")

urlpatterns = [
    path("help/faqs/", views.DriverFAQListView.as_view(), name="driver-help-faqs"),
    path("", include(router.urls))
]

