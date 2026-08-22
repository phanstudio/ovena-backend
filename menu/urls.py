from django.urls import path, include
import menu.views as views
import menu.views.business as bmenuview
import menu.views.delete as deleteview
from business_api.routers import BaseBranchRouter

from .views.tagging import (
    BusinessTagSuggestionsView,
    CategoryTagsUpdateView,
    GlobalTagCreateView,
    NewTagSuggestionsView,
    TagGroupListCreateView,
    TagGroupDetailView,
    GlobalTagListView,
    GlobalTagDeleteView,
    CategorySearchView,
    TagGroupListView
)

router = BaseBranchRouter("")

business_urls = [
    *router.register("availability", bmenuview.AvailabilityListView),
    *router.register("availability/bulk-update", bmenuview.AvaliabilityView),
    path(
        "business/menu-list/",bmenuview.BusinessMenuView.as_view(),name="business-menu-list",
    ),
    path(
        "staff/menu-list/",bmenuview.BusinessStaffMenuView.as_view(),name="staff-menu-list",
    ),
    path(
        "staff/order/<int:id>/",bmenuview.OrderRetrieveView.as_view(),name="staff-order-detail",
    ),
    path(
        "staff/order/history/",bmenuview.OrderHistoryView.as_view(),name="staff-order-history",
    ),
    path("business/bulk-delete/", deleteview.BulkDeleteMenuView.as_view(), name="bulk-delete-menu"),
    path("business/bulk-delete/images/", deleteview.BulkDeleteMenuImagesView.as_view(), name="bulk-delete-menu-images"),
]

customer_urls = [
    # Homepage with sections
    path('homepage/', views.HomePageView.as_view(), name='homepage'),
    
    # Infinite scroll list (ultra-lightweight)
    path('businesses/', views.BusinessListView.as_view(), name='business-list'),
    
    # List with menu names (no addons/variants)
    path('businesses/with-menus/', views.BusinessListWithMenuNamesView.as_view(), name='business-list-with-menus'),
    
    # Search and filter
    path('businesses/search/', views.BusinessSearchView.as_view(), name='business-search'),
    
    # Detail page (full menu)
    path('businesses/<int:business_id>/', views.BusinessDetailView.as_view(), name='business-detail'),
]

category_urls = [
    path("businesses/<int:business_id>/tag-suggestions/", BusinessTagSuggestionsView.as_view()),
    path("categories/<int:category_id>/tags/", CategoryTagsUpdateView.as_view()),
    path("tags/new-tag-suggestions/", NewTagSuggestionsView.as_view()),

    # Tag groups
    path("tag-groups/",TagGroupListCreateView.as_view(),name="tag-group-list-create",),
    path("tag-groups/<int:pk>/",TagGroupDetailView.as_view(),name="tag-group-detail",),

    # Global tags
    path("tags/", GlobalTagCreateView.as_view()),
    path("global-tags/",GlobalTagListView.as_view(),name="global-tag-list",),
    path("global-tags/<int:pk>/",GlobalTagDeleteView.as_view(),name="global-tag-delete",),

    #customer views
    path("categories/search/",CategorySearchView.as_view(),name="category-search",),
    path("categories/tag/list",TagGroupListView.as_view(),name="tag-list",),
]

urlpatterns = [
    path("restaurant-order/", views.ResturantOrderView.as_view(), name="restaurant-order"),
    path("driver-order/", views.DriverOrderView.as_view(), name="driver-order"),
    path("order/", views.OrderView.as_view(), name="order"),
    path("orders/<int:order_id>/", views.OrderView.as_view(), name="order-detail"),
    path("order/payment/<int:order_id>/", views.OrderPaymentView.as_view(), name="order-payment"),
    path("orders/retry-payment/", views.PaymentRetryView.as_view(), name="order-retry-payment",),
    path("order/<int:order_id>/cancel/",views.OrderCancelView.as_view(),name="order-cancel",),
    path("update-menus/", views.UpdateMenusView.as_view(), name="update-menus"),
    path("", include(business_urls)),
    path("", include(customer_urls)),
    path("cat/", include(category_urls)),
]
