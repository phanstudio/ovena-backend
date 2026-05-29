from django.urls import path
from coupons_discount.views import (
    AdminCouponCreateView, AdminCouponsListView, 
    AdminCouponUpdateView, AdminCouponWheelCreateView, 
    AdminCouponWheelDetailView, AdminCouponWheelListView, 
    AdminCouponWheelUpdateView
)

urlpatterns = [
    path("wheel/<int:pk>/", AdminCouponWheelDetailView.as_view(), name="coupon-wheel-detail"),
    path("wheel/all/", AdminCouponWheelListView.as_view(), name="coupon-wheel-all"),
    path("create/", AdminCouponCreateView.as_view(), name="coupon-create"),
    path("update/<int:pk>/", AdminCouponUpdateView.as_view(), name="coupon-update"),
]
