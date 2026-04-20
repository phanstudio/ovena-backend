from django.urls import path, include
import menu.views as views
import menu.views.business as bmenuview
from business_api.routers import BaseBranchRouter

router = BaseBranchRouter("")


business_urls = [
    *router.register("availability", bmenuview.AvailabilityListView),
    *router.register("availability/bulk-update", bmenuview.AvaliabilityView),
    path(
        "business/menu-list/",
        bmenuview.BusinessMenuView.as_view(),
        name="business-menu-list",
    ),
    path(
        "staff/menu-list/",
        bmenuview.BusinessStaffMenuView.as_view(),
        name="staff-menu-list",
    ),
]

urlpatterns = [
    path(
        "businesses/<int:business_id>/menus/",
        views.MenuView.as_view(),
        name="menu-list",
    ),
    path("restaurant-list/", views.RestaurantView.as_view(), name="restaurant-list"),
    path("menuitem-search/", views.SearchMenuItems.as_view(), name="menuitem-search"),
    path(
        "restaurant-order/", views.ResturantOrderView.as_view(), name="restaurant-order"
    ),
    path("driver-order/", views.DriverOrderView.as_view(), name="driver-order"),
    path("home-page/", views.HomePageView.as_view(), name="home-page"),
    path("order/", views.OrderView.as_view(), name="order"),
    path("orders/<int:order_id>/", views.OrderView.as_view(), name="order-detail"),
    path(
        "order/<int:order_id>/cancel/",
        views.OrderCancelView.as_view(),
        name="order-cancel",
    ),
    path("update-menus/", views.UpdateMenusView.as_view(), name="update-menus"),
    path("", include(business_urls)),
]
