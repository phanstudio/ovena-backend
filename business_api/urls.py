from django.urls import path

from menu.views import BatchGenerateUploadURLView, RegisterMenusPhase3View

from business_api import views


urlpatterns = [
    path("onboard/status/", views.BuisnnessOnboardingStatusView.as_view(), name="business-onboard-status"),
    path("onboard/phase1/", views.RestaurantPhase1RegisterView.as_view(), name="business-register-phase1"),
    path("onboard/phase2/", views.RestaurantPhase2OnboardingView.as_view(), name="business-register-phase2"),
    path("onboard/phase3/", RegisterMenusPhase3View.as_view(), name="business-register-menus-ob"),
    path("onboard/batch-gen-url/", BatchGenerateUploadURLView.as_view(), name="business-batch-generate-url"),
    path("branches/<int:branch_id>/hours/", views.BranchOperatingHoursView.as_view(), name="business-branch-hours"),
    path("payment/", views.RestaurantPaymentView.as_view(), name="business-payment"),
    path("wallet/balance/", views.BusinessWalletBalanceView.as_view(), name="business-wallet-balance"),
    path("wallet/withdraw/", views.BusinessWalletWithdrawalView.as_view(), name="business-wallet-withdraw"),
    path("wallet/withdrawals/", views.BusinessWalletWithdrawalHistoryView.as_view(), name="business-wallet-history"),
]

