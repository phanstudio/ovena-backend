from django.urls import path
from .views import (
    UserCouponWalletListView, CouponWheelGetView, CouponWheelSpinView,
)

urlpatterns = [
    path("list/", UserCouponWalletListView.as_view(), name="list-coupons"),
    path("wheel/", CouponWheelGetView.as_view(), name="coupon-wheel-get"),
    path("wheel/spin/", CouponWheelSpinView.as_view(), name="coupon-wheel-spin"),
]
