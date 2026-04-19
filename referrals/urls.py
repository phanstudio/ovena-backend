from django.urls import path

from referrals.views.base import ApplyReferralCodeView, MyReferralStatusView, MyReferralsListView


urlpatterns = [
    path("apply/", ApplyReferralCodeView.as_view(), name="apply-referral-code"),
    path("me/status/", MyReferralStatusView.as_view(), name="my-referral-status"),
    path("me/list/", MyReferralsListView.as_view(), name="my-referrals-list"),
]
