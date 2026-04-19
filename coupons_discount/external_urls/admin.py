from django.urls import path
from coupons_discount.views import (
    CouponCreateView, CouponUpdateView,
    CouponWheelCreateView, CouponWheelSetterView,
)

urlpatterns = [
    path("coupons/", CouponCreateView.as_view()),
    path("coupons/<int:pk>/", CouponUpdateView.as_view()),

    path("coupon-wheels/", CouponWheelCreateView.as_view()),
    path("coupon-wheels/<int:pk>/", CouponWheelSetterView.as_view()),
]
