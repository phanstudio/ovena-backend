from django.urls import path
from .views import (
    EligibleCouponsListView, CouponWheelGetView, CouponWheelSpinView,
)

urlpatterns = [
    path("coupons/eligible/", EligibleCouponsListView.as_view(), name="eligible-coupons"),
    path("coupon-wheel/", CouponWheelGetView.as_view(), name="coupon-wheel-get"),
    path("coupon-wheel/spin/", CouponWheelSpinView.as_view(), name="coupon-wheel-spin"),
]
