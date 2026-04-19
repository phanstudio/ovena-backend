from django.urls import path, include
from admin_api import views
from accounts.views import (
    jwt_views,
    PasswordResetView, PassWordResetSendView, ChangePasswordView
)
import referrals.views.admin as ref_views


token_urls = [
    path("rotate-token/", jwt_views.RotateTokenView.as_view(), name="rotate-token"),
    path("refresh/", jwt_views.RefreshTokenView.as_view(), name="refresh"),
    path("logout/", jwt_views.LogoutView.as_view(), name="logout"), # for 
]

referral_url = [
    # 🔥 users eligible for payout
    path(
        "users/",
        ref_views.AdminReferralUserListView.as_view(),
        name="admin-referral-users"
    ),

    # 💰 create payout
    path(
        "payout/",
        ref_views.AdminReferralPaymentView.as_view(),
        name="admin-referral-payout-create"
    ),

    # 🧪 verify payout integrity
    path(
        "payouts/<int:payout_id>/verify/",
        ref_views.AdminVerifyPayoutView.as_view(),
        name="admin-referral-payout-verify"
    ),

    # 📊 list payouts
    path(
        "payouts/",
        views.AdminReferralPayoutListView.as_view(),
        name="admin-referral-payout-list"
    ),

    # 🔍 payout detail
    path(
        "payouts/<int:pk>/",
        views.AdminReferralPayoutDetailView.as_view(),
        name="admin-referral-payout-detail"
    ),
]

urlpatterns = [
    path("profile/", views.UserProfileView.as_view(), name="app-admin-profile"),
    path("profile/update/", views.UpdateAppAdmin.as_view(), name="app-admin-update"),
    path("login/", views.AdminLoginView.as_view(), name="app-admin-login"),

    path("", include(token_urls)),
    path("referrals/", include(ref_views)),
    path("password-reset/", PasswordResetView.as_view(), name="password-reset"),
    path("password-reset/send/", PassWordResetSendView.as_view(), name="password-reset-send"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("admin/", include("coupons_discount.external_urls.admin")),
    path("", include("support_center.urls.admin")),
]
