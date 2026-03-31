from django.urls import include, path

from driver_api import views

urlpatterns = [
    path("dashboard/", views.DriverDashboardView.as_view(), name="driver-dashboard"),
    path("profile/", views.DriverProfileView.as_view(), name="driver-profile"),
    path("availability/", views.DriverAvailabilityView.as_view(), name="driver-availability"),
    path("", include("support_center.urls.driver")),
    path("", include("notifications.driver_urls")),
    path("earnings/summary/", views.DriverEarningsSummaryView.as_view(), name="driver-earnings-summary"),
    path("earnings/history/", views.DriverEarningsHistoryView.as_view(), name="driver-earnings-history"),
    path("withdrawals/eligibility/", views.DriverWithdrawEligibilityView.as_view(), name="driver-withdrawals-eligibility"),
    path("withdrawals/", views.DriverWithdrawListCreateView.as_view(), name="driver-withdrawals"),
    path("withdrawals/<int:withdrawal_id>/", views.DriverWithdrawDetailView.as_view(), name="driver-withdrawal-detail"),
    path("withdrawals/paystack/webhook/", views.PaystackWithdrawalWebhookView.as_view(), name="driver-withdrawals-paystack-webhook"),
    path("analysis/performance/", views.DriverAnalysisPerformanceView.as_view(), name="driver-analysis-performance"),
]
