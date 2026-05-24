from django.urls import path
from ratings.views import SubmitOrderRatingsView,MyBranchRatingsView, MyDriverRatingsView

urlpatterns = [
    path("rate-order/", SubmitOrderRatingsView.as_view(), name="rate-order"),
    path("me/driver-ratings/", MyDriverRatingsView.as_view(), name="my-driver-ratings"),
    path("me/branch-ratings/", MyBranchRatingsView.as_view(), name="my-branch-ratings"),
]
