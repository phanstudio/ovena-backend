from django.urls import path
from .. import views

prefix = "business-"
urlpatterns = [
    path("subscription/", views.BusinessCreateSubscriptionView.as_view(), name=prefix+"subscription-create"),
    path("subscription/cancle/", views.BusinessCancelSubscriptionView.as_view(), name=prefix+"subscription-cancle"),
    path("subscription/current/", views.BusinessCurrentSubscriptionView.as_view(), name=prefix+"subscription-current"),
    path("invoice/history/", views.BusinessInvoiceHistoryView.as_view(), name=prefix+"invoice-history"),
    path("invoice/retry/<int:invoice_id>/", views.BusinessRetryInvoicePaymentView.as_view(), name=prefix+"invoice-retry"),
    path("update/card/link/", views.BusinessSubscriptionUpdateCardView.as_view(), name=prefix+"update-card"),
    path("plans/list/", views.BusinessPlanListView.as_view(), name=prefix+"plan-list"),
]
