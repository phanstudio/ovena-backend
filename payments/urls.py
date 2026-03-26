from django.urls import path
from payments import views

urlpatterns = [
    # Sales
    path("sales/initialize/",          views.initialize_sale_view,    name="sale-initialize"),
    path("sales/<uuid:sale_id>/complete/", views.complete_service_view, name="sale-complete"),
    path("sales/<uuid:sale_id>/refund/",   views.refund_sale_view,      name="sale-refund"),

    # Wallet
    path("wallet/balance/",            views.balance_view,              name="wallet-balance"),
    path("wallet/withdraw/",           views.request_withdrawal_view,   name="wallet-withdraw"),
    path("wallet/withdrawals/",        views.withdrawal_history_view,   name="wallet-history"),

    # Webhooks
    path("webhooks/paystack/",         views.paystack_webhook_view,     name="paystack-webhook"),
]
