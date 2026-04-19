from django.urls import path
from admin_api import views
import referrals.views.admin as ref_views

urlpatterns = [
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
