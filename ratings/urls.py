# ratings/urls.py
from django.urls import path
from .views import DriverRatingsView, BranchRatingsView

urlpatterns = [
    path("driver-ratings/", DriverRatingsView.as_view(), name="driver-ratings"),
    path("branch-ratings/", BranchRatingsView.as_view(), name="branch-ratings"),
]
