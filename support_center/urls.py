from django.urls import path

from support_center import views


buisness_urlpatterns = [
    path("support/tickets/", views.BusinessSupportTicketListCreateView.as_view(), name="business-support-tickets"),
    path("support/tickets/<int:ticket_id>/", views.SupportTicketDetailView.as_view(), name="business-support-ticket-detail"),
    path(
        "support/tickets/<int:ticket_id>/messages/",
        views.SupportTicketMessageListCreateView.as_view(),
        name="business-support-ticket-messages",
    ),
]

driver_urlpatterns = [
    path("help/faqs/", views.DriverFAQListView.as_view(), name="driver-help-faqs"),
    path("help/tickets/", views.DriverSupportTicketListCreateView.as_view(), name="driver-help-tickets"),
    path("help/tickets/<int:ticket_id>/", views.SupportTicketDetailView.as_view(), name="driver-help-ticket-detail"),
    path(
        "help/tickets/<int:ticket_id>/messages/",
        views.SupportTicketMessageListCreateView.as_view(),
        name="driver-help-ticket-messages",
    ),
]
