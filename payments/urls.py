from django.urls import path
from payments import views
from .callback import paystack

urlpatterns = [
    # Sales
    path("sales/initialize/",          views.SaleInitializeView.as_view(),    name="sale-initialize"),
    path("sales/<uuid:sale_id>/complete/", views.SaleCompleteView.as_view(),  name="sale-complete"),
    path("sales/<uuid:sale_id>/refund/",   views.SaleRefundView.as_view(),    name="sale-refund"),

    # Wallet
    path("wallet/balance/",            views.WalletBalanceView.as_view(),     name="wallet-balance"),
    path("wallet/withdraw/",           views.RequestWithdrawalView.as_view(),  name="wallet-withdraw"),
    path("wallet/withdrawals/",        views.WithdrawalHistoryView.as_view(), name="wallet-history"),

    # Webhooks
    path("webhooks/paystack/",         views.PaystackWebhookView.as_view(),   name="paystack-webhook"),

    # Callbacks
    path("payments/paystack/callback/",paystack.paystack_callback,            name="paystack-callback"),

    # Banks
    path("banks/",                     views.ListBanks.as_view(),              name="list-banks"),

    # Admin Withdrawal Review & Resolution
    path("admin/withdrawals/<uuid:withdrawal_id>/review/", views.AdminReviewWithdrawalView.as_view(), name="admin-withdrawal-review"),
]
