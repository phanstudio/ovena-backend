from django.urls import path, include
from admin_api import views
from accounts.views import (
    jwt_views,
    PasswordResetView, PassWordResetSendView, ChangePasswordView
)

token_urls = [
    path("rotate-token/", jwt_views.RotateTokenView.as_view(), name="rotate-token"),
    path("refresh/", jwt_views.RefreshTokenView.as_view(), name="refresh"),
    path("logout/", jwt_views.LogoutView.as_view(), name="logout"), # for 
]

urlpatterns = [
    path("profile/", views.UserProfileView.as_view(), name="app-admin-profile"),
    path("profile/update/", views.UpdateAppAdmin.as_view(), name="app-admin-update"),
    path("login/", views.AdminLoginView.as_view(), name="app-admin-login"),

    # dashboard + stats
    path("dashboard/stats/", views.AdminDashboardStatsView.as_view(), name="admin-dashboard-stats"),

    # user management
    path("users/", views.AdminUserListView.as_view(), name="admin-users"),
    path("users/<int:user_id>/", views.AdminUserDetailView.as_view(), name="admin-user-detail"),

    # employee management
    path("employees/drivers/", views.AdminDriverListView.as_view(), name="admin-drivers"),
    path("employees/drivers/<int:driver_id>/onboarding/review/", views.AdminDriverOnboardingReviewView.as_view(), name="admin-driver-onboarding-review"),
    path("employees/businesses/", views.AdminBusinessListView.as_view(), name="admin-businesses"),
    path("employees/businesses/<int:business_id>/", views.AdminBusinessUpdateView.as_view(), name="admin-business-update"),

    # withdrawals system
    path("withdrawals/", views.AdminWithdrawalListView.as_view(), name="admin-withdrawals"),
    path("withdrawals/<uuid:withdrawal_id>/", views.AdminWithdrawalDetailView.as_view(), name="admin-withdrawal-detail"),
    path("withdrawals/<uuid:withdrawal_id>/retry/", views.AdminWithdrawalRetryView.as_view(), name="admin-withdrawal-retry"),
    path("withdrawals/<uuid:withdrawal_id>/mark-paid/", views.AdminWithdrawalMarkPaidView.as_view(), name="admin-withdrawal-mark-paid"),
    path("withdrawals/<uuid:withdrawal_id>/mark-failed/", views.AdminWithdrawalMarkFailedView.as_view(), name="admin-withdrawal-mark-failed"),
    path("withdrawals/batch/execute/", views.AdminWithdrawalBatchExecuteView.as_view(), name="admin-withdrawals-batch-execute"),
    path("withdrawals/reconcile/", views.AdminWithdrawalReconcileView.as_view(), name="admin-withdrawals-reconcile"),

    # notifications
    path("notifications/", views.AdminNotificationListView.as_view(), name="admin-notifications"),
    path("notifications/send/", views.AdminSendNotificationView.as_view(), name="admin-notifications-send"),

    path("", include(token_urls)),
    path("password-reset/", PasswordResetView.as_view(), name="password-reset"),
    path("password-reset/send/", PassWordResetSendView.as_view(), name="password-reset-send"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("", include("coupons_discount.external_urls.admin")),
    path("", include("support_center.urls.admin")),
    path("referrals/", include("referrals.admin_urls")),
]
