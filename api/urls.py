from django.urls import path, include

urlpatterns = [
    path("accounts/", include("accounts.urls")),
    path("business/", include("business_api.urls")),
    path("menu/", include("menu.urls")),
    path("driver/", include("driver_api.urls")),
    path("referrals/", include("referrals.urls")),
    path("", include("coupons_discount.urls")),
    path("", include("payments.urls")),
]
