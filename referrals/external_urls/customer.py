from django.urls import path

from referrals.views.base import ApplyReferralCodeView, CustomerMyReferralStatusView, MyReferralsListView


urlpatterns = [
    # path("apply/", ApplyReferralCodeView.as_view(), name="apply-referral-code"),
    path("me/status/", CustomerMyReferralStatusView.as_view(), name="my-referral-status"),
    path("me/list/", MyReferralsListView.as_view(), name="my-referrals-list"),
]
