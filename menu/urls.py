from django.urls import path
import menu.views as views

urlpatterns = [
    path("restaurants/<int:restaurant_id>/menus/", views.MenuView.as_view(), name="menu-list"),
    path("restaurant-list/", views.RestaurantView.as_view(), name="restaurant-list"),
    path("menuitem-search/", views.SearchMenuItems.as_view(), name="menuitem-search"),
]
