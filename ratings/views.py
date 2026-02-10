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
from authflow.decorators import subuser_authentication
from authflow.permissions import ReadScopePermission
from authflow.authentication import CustomDriverAuth

class SubmitOrderRatingsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        s = SubmitOrderRatingsSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        order = get_object_or_404(
            Order.objects.select_related("driver", "branch"),
            id=s.validated_data["order_id"],
        )
        rater = request.user.customerprofile

        # business rules (adjust to your app)
        if getattr(order, "customer_id", None) != rater.id:
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

class MyDriverRatingsView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DriverRatingReadSerializer

    def get_queryset(self):
        rater = self.request.user.customerprofile
        return DriverRating.objects.filter(rater=rater).select_related("driver", "order").order_by("-created_at")

class MyBranchRatingsView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BranchRatingReadSerializer

    def get_queryset(self):
        rater = self.request.user.customerprofile
        return BranchRating.objects.filter(rater=rater).select_related("branch", "order").order_by("-created_at")

class DriverRatingsView(ListAPIView):
    authentication_classes = [CustomDriverAuth]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DriverRatingReadSerializer

    def get_queryset(self):
        driver = self.request.user.driver_profile
        return DriverRating.objects.filter(driver=driver).select_related("driver", "order").order_by("-created_at")

@subuser_authentication
class BranchRatingsView(ListAPIView):
    permission_classes = [ReadScopePermission]
    required_scopes = ["ratings:read"]
    serializer_class = BranchRatingReadSerializer

    def get_queryset(self):
        _, primaryagent = self.get_linkeduser()
        self.request.user
        return BranchRating.objects.filter(branch=primaryagent.branch).select_related("branch", "order").order_by("-created_at")











# 
# branches/views.py
from django.db.models import Avg, Count
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from branches.models import Branch
from branches.serializers import BranchSerializer


class TopBranchesView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = BranchSerializer

    def get_queryset(self):
        return (
            Branch.objects
            .annotate(
                rating_avg=Avg("ratings_received__stars"),
                rating_count=Count("ratings_received__id"),
            )
            .order_by("-rating_avg", "-rating_count")
        )



# branches/views.py
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from branches.models import Branch
from branches.serializers import BranchSerializer


class TopBranchesView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = BranchSerializer

    def get_queryset(self):
        qs = Branch.objects.all()

        # optional: hide branches with too few ratings
        min_count = int(self.request.query_params.get("min_count", 0))
        if min_count > 0:
            qs = qs.filter(rating_count__gte=min_count)

        return qs.order_by("-avg_rating", "-rating_count", "id")
