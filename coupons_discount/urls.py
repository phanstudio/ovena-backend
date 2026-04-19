from django.urls import path
from .views import (
    EligibleCouponsListView, CouponWheelGetView, CouponWheelSpinView,
)

urlpatterns = [
    path("eligible/", EligibleCouponsListView.as_view(), name="eligible-coupons"),
    path("wheel/", CouponWheelGetView.as_view(), name="coupon-wheel-get"),
    path("wheel/spin/", CouponWheelSpinView.as_view(), name="coupon-wheel-spin"),
]
