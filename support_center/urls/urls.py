from django.urls import path, include
from support_center import views
from rest_framework.routers import DefaultRouter
from support_center.views import DriverSupportTicketViewSet


buisness_urlpatterns = [
    path("support/tickets/", views.BusinessSupportTicketListCreateView.as_view(), name="business-support-tickets"),
    path("support/tickets/<int:ticket_id>/", views.SupportTicketDetailView.as_view(), name="business-support-ticket-detail"),
    path(
        "support/tickets/<int:ticket_id>/messages/",
        views.SupportTicketMessageListCreateView.as_view(),
        name="business-support-ticket-messages",
    ),
]
