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
        "order/<int:order_id>/reorder/", views.ReorderView.as_view(), name="customer-order-reorder"
    ),
    path("order/calculations/", views.OrderCalculationsView.as_view(), name="order-calculations"),
    path(
        "generate/link/", views.GenerateLinkView.as_view(), name="customer-generate-link"
    ),
    path("ref/", include("referrals.external_ulrs.customer")),
    path("rating/", include("ratings.external_ulrs.customer")),
    path("", include("support_center.urls.customer")),
    path("", include("notifications.urls.customer")),
    path("", include("payments.subscriptions.urls.client")),
    path("favorite/", views.FavoriteCreateView.as_view(), name="favorite"),
    path("favorite/remove/", views.FavoriteRemoveView.as_view(), name="favorite-remove"),
    path("favorite/list/", views.FavoriteListView.as_view(), name="favorite-list"),
    path("staff/detail/<int:id>/", views.StoreDetailsView.as_view(), name="staff-detail"),
    path("points/", include("points.external_ulrs.customer")),
]
