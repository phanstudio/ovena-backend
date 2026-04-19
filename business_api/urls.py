from django.urls import path, include

# from menu.views import BatchGenerateUploadURLView, RegisterMenusPhase3View

from business_api import views
from .routers import BaseBranchRouter

router = BaseBranchRouter()

branch_urlpatterns = [
    *router.register("hours", views.BranchOperatingHoursView),
    *router.register("close", views.BranchClosedView),
    # no branch (admin = all, staff = own) # might add all later
]

urlpatterns = [
    # path("onboard/status/", views.BuisnnessOnboardingStatusView.as_view(), name="business-onboard-status"),
    # path("onboard/phase1/", views.RestaurantPhase1RegisterView.as_view(), name="business-register-phase1"),
    # path("onboard/phase2/", views.RestaurantPhase2OnboardingView.as_view(), name="business-register-phase2"),
    # path("onboard/phase3/", RegisterMenusPhase3View.as_view(), name="business-register-menus-ob"),
    # path("onboard/batch-gen-url/", BatchGenerateUploadURLView.as_view(), name="business-batch-generate-url"),
    path("dashboard/", views.BusinessDashboardView.as_view(), name="business-dashboard"),
    path("analysis/store/", views.BusinessStoreAnalysisView.as_view(), name="business-store-analysis"),
    path("wallet/transaction-pin/", views.BusinessTransactionPinView.as_view(), name="business-transaction-pin"),
    path("payment/", views.RestaurantPaymentView.as_view(), name="business-payment"),
    path("payment/verify/", views.RestaurantPaymentReceiverView.as_view(), name="business-payment-verify"),
    path("wallet/balance/", views.BusinessWalletBalanceView.as_view(), name="business-wallet-balance"),
    path("wallet/transactions/", views.BusinessTransactionHistoryView.as_view(), name="business-wallet-transactions"),
    path("wallet/withdraw/eligibility/", views.BuisnessWithdrawEligibilityView.as_view(), name="business-withdrawal-eligibility"),
    path("wallet/withdraw/", views.BusinessWalletWithdrawalView.as_view(), name="business-wallet-withdraw"),
    path("wallet/withdrawals/", views.BusinessWalletWithdrawalHistoryView.as_view(), name="business-wallet-history"),
    path("list-branches/", views.BranchListView.as_view(), name="list-branches"),
    path("branch/edit/", views.BranchCreateUpdateView.as_view(), name="branch-edit"),
    path("branches/", include(branch_urlpatterns)),
    path("", include("support_center.urls.buisness")),
    path("", include("notifications.urls.buisness")),
    path("staff/list/", views.StaffListView.as_view(), name="staff-list"),
    path("staff/revoke/", views.StaffRevokeView.as_view(), name="staff-revoke"),
    path("admin/update/", views.BuisnessAdminUpdateView.as_view(), name="buis-admin-update"),
    path("admin/update/verify/", views.BuisnessAdminUpdateReceiverView.as_view(), name="buis-admin-update-verify"),
]
