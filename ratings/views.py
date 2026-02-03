from django.shortcuts import render

# Create your views here.

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework import status

from menu.models import Order
from .serializers import (
    SubmitOrderRatingsSerializer,
    DriverRatingSerializer,
    BranchRatingSerializer,
)
from .services import RatingService


class SubmitOrderRatingsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = SubmitOrderRatingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order_id = serializer.validated_data["order_id"]
        driver_payload = serializer.validated_data.get("driver")
        branch_payload = serializer.validated_data.get("branch")

        # Your app likely has a CustomerProfile relation:
        rater = request.user.customerprofile

        # Load order
        order = (
            Order.objects
            .select_related("driver", "branch")
            .get(id=order_id)
        )

        # Important business rules you probably want:
        # - only the order owner can rate
        if hasattr(order, "customer_id") and order.customer_id != rater.id:
            return Response({"detail": "You cannot rate this order."}, status=status.HTTP_403_FORBIDDEN)

        # - only rate delivered/completed orders
        if getattr(order, "status", None) not in ("delivered", "completed"):
            return Response({"detail": "You can only rate after delivery."}, status=status.HTTP_400_BAD_REQUEST)

        results = RatingService.submit_for_order(
            order=order,
            rater=rater,
            driver_payload=driver_payload,
            branch_payload=branch_payload,
        )

        response = {}
        if "driver_rating" in results:
            response["driver_rating"] = DriverRatingSerializer(results["driver_rating"]).data
        if "branch_rating" in results:
            response["branch_rating"] = BranchRatingSerializer(results["branch_rating"]).data

        return Response(response, status=status.HTTP_200_OK)




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
