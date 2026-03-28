from django.urls import path, include
import menu.views as views
import menu.views.business as bmenuview


business_urls =[
    path("business/menu-list", bmenuview.MenuView.as_view(), name="business-menu-list"),

]

urlpatterns = [
    path("businesses/<int:business_id>/menus/", views.MenuView.as_view(), name="menu-list"),
    path("restaurant-list/", views.RestaurantView.as_view(), name="restaurant-list"),
    path("menuitem-search/", views.SearchMenuItems.as_view(), name="menuitem-search"),
    path("restaurant-order/", views.ResturantOrderView.as_view(), name="restaurant-order"),
    path("driver-order/", views.DriverOrderView.as_view(), name="driver-order"),

    path("home-page/", views.HomePageView.as_view(), name="home-page"),

    path("order/", views.OrderView.as_view(), name="order"),
    path("orders/<int:order_id>/", views.OrderView.as_view(), name="order-detail"),
    path("order/<int:order_id>/cancel/", views.OrderCancelView.as_view(), name="order-cancel"),

    path("update-menus/", views.UpdateMenusView.as_view(), name="update-menus"),

    path("", include(business_urls)),
]
