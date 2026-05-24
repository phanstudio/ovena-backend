# ratings/views.py
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView

from menu.models import Order
from .models import DriverRating, BranchRating
from .serializers import (
    SubmitOrderRatingsSerializer,
    DriverRatingReadSerializer,
    BranchRatingReadSerializer,
)
from .services import RatingService
from authflow.permissions import IsBusinessStaff
from authflow.authentication import CustomDriverAuth, CustomBStaffAuth
from common.customer.view import BaseCustomerAPIView

class SubmitOrderRatingsView(BaseCustomerAPIView):
    serializer_class = SubmitOrderRatingsSerializer
    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)

        order = get_object_or_404(
            Order.objects.select_related("driver", "branch"),
            id=s.validated_data["order_id"],
        )
        # rater = request.user.customerprofile
        rater = self.get_customer_profile(request)

        if order.orderer != rater:
            return Response({"detail": "You cannot rate this order."}, status=status.HTTP_403_FORBIDDEN)

        if getattr(order, "status", None) not in ("delivered", "completed"):
            return Response({"detail": "You can only rate after delivery."}, status=status.HTTP_400_BAD_REQUEST)

        results = RatingService.submit_for_order(
            order=order,
            rater=rater,
            driver_payload=s.validated_data.get("driver"),
            branch_payload=s.validated_data.get("branch"),
        )

        payload = {}
        if results.get("driver_rating"):
            payload["driver_rating"] = DriverRatingReadSerializer(results["driver_rating"]).data
        if results.get("branch_rating"):
            payload["branch_rating"] = BranchRatingReadSerializer(results["branch_rating"]).data

        return Response(payload, status=status.HTTP_200_OK)

class MyDriverRatingsView(BaseCustomerAPIView, ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DriverRatingReadSerializer

    def get_queryset(self):
        rater = self.get_customer_profile(self.request)
        return DriverRating.objects.filter(rater=rater).select_related("driver", "order").order_by("-created_at")

class MyBranchRatingsView(BaseCustomerAPIView, ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BranchRatingReadSerializer

    def get_queryset(self):
        rater = self.get_customer_profile(self.request)
        return BranchRating.objects.filter(rater=rater).select_related("branch", "order").order_by("-created_at")

class DriverRatingsView(ListAPIView):
    authentication_classes = [CustomDriverAuth]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DriverRatingReadSerializer

    def get_queryset(self):
        driver = self.request.user.driver_profile
        return DriverRating.objects.filter(driver=driver).select_related("driver", "order").order_by("-created_at")

class BranchRatingsView(ListAPIView):
    authentication_classes = [CustomBStaffAuth]
    permission_classes = [IsBusinessStaff]
    serializer_class = BranchRatingReadSerializer

    def get_queryset(self):
        _, primaryagent = self.get_linkeduser()
        self.request.user
        return BranchRating.objects.filter(branch=primaryagent.branch).select_related("branch", "order").order_by("-created_at")
