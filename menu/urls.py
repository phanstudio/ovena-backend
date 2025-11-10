from django.urls import path, include
import menu.views as views

payment_urls =[
    path("paystack/webhook/", views.paystack_webhook, name="paystack-webhook"),
]

urlpatterns = [
    path("restaurants/<int:restaurant_id>/menus/", views.MenuView.as_view(), name="menu-list"),
    path("restaurant-list/", views.RestaurantView.as_view(), name="restaurant-list"),
    path("menuitem-search/", views.SearchMenuItems.as_view(), name="menuitem-search"),
    path("register-menu/", views.MenuRegistrationView.as_view(), name="register-menu"),
    path("restaurant-order/", views.ResturantOrderView.as_view(), name="restaurant-order"),
    path("", include(payment_urls)),
]
