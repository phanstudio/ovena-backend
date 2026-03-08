from django.urls import path

from driver_api import views


urlpatterns = [
    path("dashboard/", views.DriverDashboardView.as_view(), name="driver-dashboard"),
    path("profile/", views.DriverProfileView.as_view(), name="driver-profile"),
    path("availability/", views.DriverAvailabilityView.as_view(), name="driver-availability"),
    path("help/faqs/", views.DriverFAQListView.as_view(), name="driver-help-faqs"),
    path("help/tickets/", views.SupportTicketListCreateView.as_view(), name="driver-help-tickets"),
    path("help/tickets/<int:ticket_id>/", views.SupportTicketDetailView.as_view(), name="driver-help-ticket-detail"),
    path(
        "help/tickets/<int:ticket_id>/messages/",
        views.SupportTicketMessageListCreateView.as_view(),
        name="driver-help-ticket-messages",
    ),
    path("notifications/", views.DriverNotificationListView.as_view(), name="driver-notifications"),
    path("notifications/unread-count/", views.DriverNotificationUnreadCountView.as_view(), name="driver-notifications-unread-count"),
    path("notifications/<int:notification_id>/read/", views.DriverNotificationMarkReadView.as_view(), name="driver-notification-read"),
    path("notifications/read-all/", views.DriverNotificationReadAllView.as_view(), name="driver-notification-read-all"),
    path("earnings/summary/", views.DriverEarningsSummaryView.as_view(), name="driver-earnings-summary"),
    path("earnings/history/", views.DriverEarningsHistoryView.as_view(), name="driver-earnings-history"),
    path("withdrawals/eligibility/", views.DriverWithdrawEligibilityView.as_view(), name="driver-withdrawals-eligibility"),
    path("withdrawals/", views.DriverWithdrawListCreateView.as_view(), name="driver-withdrawals"),
    path("withdrawals/<int:withdrawal_id>/", views.DriverWithdrawDetailView.as_view(), name="driver-withdrawal-detail"),
    path("withdrawals/paystack/webhook/", views.PaystackWithdrawalWebhookView.as_view(), name="driver-withdrawals-paystack-webhook"),
    path("analysis/performance/", views.DriverAnalysisPerformanceView.as_view(), name="driver-analysis-performance"),
]
