from django.urls import path

from support_center import views


urlpatterns = [
    path("help/faqs/", views.DriverFAQListView.as_view(), name="driver-help-faqs"),
    path("help/tickets/", views.SupportTicketListCreateView.as_view(), name="driver-help-tickets"),
    path("help/tickets/<int:ticket_id>/", views.SupportTicketDetailView.as_view(), name="driver-help-ticket-detail"),
    path(
        "help/tickets/<int:ticket_id>/messages/",
        views.SupportTicketMessageListCreateView.as_view(),
        name="driver-help-ticket-messages",
    ),
]
