from django.urls import path
from .. import views

urlpatterns = [ # /client
    path("subscription/", views.CreateSubscriptionView.as_view(), name="subscription-create"),
    path("subscription/cancle/", views.CancelSubscriptionView.as_view(), name="subscription-cancle"),
    path("subscription/current/", views.CurrentSubscriptionView.as_view(), name="subscription-current"),
    path("invoice/history/", views.InvoiceHistoryView.as_view(), name="invoice-history"),
    path("invoice/retry/<int:invoice_id>", views.RetryInvoicePaymentView.as_view(), name="invoice-retry"),
    path("update/card/link/", views.SubscriptionUpdateCardView.as_view(), name="update-card"),
    path("plans/list/", views.ClientPlanListView.as_view(), name="client-plan-list"),
]
