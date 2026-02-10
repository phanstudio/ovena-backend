from django.urls import path
from .views import (
    EligibleCouponsListView, CouponWheelGetView, CouponWheelSpinView,
    CouponCreateView, CouponUpdateView,
    CouponWheelCreateView, CouponWheelSetterView,
)

urlpatterns = [
    path("coupons/eligible/", EligibleCouponsListView.as_view(), name="eligible-coupons"),
    path("coupon-wheel/", CouponWheelGetView.as_view(), name="coupon-wheel-get"),
    path("coupon-wheel/spin/", CouponWheelSpinView.as_view(), name="coupon-wheel-spin"),

    path("admin/coupons/", CouponCreateView.as_view()),
    path("admin/coupons/<int:pk>/", CouponUpdateView.as_view()),

    path("admin/coupon-wheels/", CouponWheelCreateView.as_view()),
    path("admin/coupon-wheels/<int:pk>/", CouponWheelSetterView.as_view()),
]
