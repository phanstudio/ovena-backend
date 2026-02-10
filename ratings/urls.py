# ratings/urls.py
from django.urls import path
from .views import SubmitOrderRatingsView, DriverRatingsView, BranchRatingsView

urlpatterns = [
    path("rate-order/", SubmitOrderRatingsView.as_view(), name="rate-order"),
    # path("me/driver-ratings/", MyDriverRatingsView.as_view(), name="my-driver-ratings"),
    # path("me/branch-ratings/", MyBranchRatingsView.as_view(), name="my-branch-ratings"),
    path("driver-ratings/", DriverRatingsView.as_view(), name="driver-ratings"),
    path("branch-ratings/", BranchRatingsView.as_view(), name="branch-ratings"),
]
