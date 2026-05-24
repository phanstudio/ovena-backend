from django.urls import path, include
from . import views

urlpatterns = [
    path(
        "order/history/", views.OrderHistoryView.as_view(), name="customer-order-history"
    ),
    path(
        "order/<int:id>/", views.OrderRetrieveView.as_view(), name="customer-order"
    ),
    path(
        "generate/link/", views.GenerateLinkView.as_view(), name="customer-generate-link"
    ),
    path("ref/", include("referrals.external_ulrs.customer")),
    path("rating/", include("ratings.external_ulrs.customer")),
    path("", include("support_center.urls.customer")),
    path("", include("notifications.urls.customer")),
]
