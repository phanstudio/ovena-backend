import random

from django.db import transaction
from django.db.models import Q, Prefetch

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics, permissions, filters

from .models import Coupons, CouponWheel, UserCouponWallet
from .serializers import (
    CouponSerializer, CouponCreateUpdateSerializer,
    CouponWheelSerializer, CouponWheelSetSerializer,
    UserCouponWalletSerializer, CouponWheelBaseSerializer,
)
from .services import WheelService, eligible_coupon_q, eligible_coupon_for_wheel_with_min_lifetime_q

from common.pagination import StandardResultsSetPagination
from common.customer.view import BaseCustomerAPIView
from admin_api.views import BaseAppAdminAPIView


# Admin coupons functions
class AdminCouponCreateView(BaseAppAdminAPIView, generics.CreateAPIView):
    """
    POST /api/admin/coupons/
    """
    serializer_class = CouponCreateUpdateSerializer


class AdminCouponUpdateView(BaseAppAdminAPIView, generics.UpdateAPIView):
    """
    PATCH/PUT /api/admin/coupons/<id>/
    """
    serializer_class = CouponCreateUpdateSerializer
    queryset = Coupons.objects.all()


class AdminCouponWheelUpdateView(BaseAppAdminAPIView, generics.UpdateAPIView):
    """
    PATCH /api/admin/coupon-wheels/<id>/
    Body can include:
      - max_entries_amount
      - coupon_ids: [1,2,3]
      - is_active: true/false  (if true, will deactivate other wheels)
    """
    serializer_class = CouponWheelSetSerializer
    queryset = CouponWheel.objects.all()

    @transaction.atomic
    def perform_update(self, serializer):
        wheel = serializer.instance
        new_is_active = serializer.validated_data.get("is_active", wheel.is_active)

        # If activating this wheel, deactivate others
        if new_is_active is True:
            CouponWheel.objects.exclude(pk=wheel.pk).update(is_active=False)

        serializer.save()


class AdminCouponWheelCreateView(BaseAppAdminAPIView, generics.CreateAPIView):
    """
    POST /api/admin/coupon-wheels/
    """
    serializer_class = CouponWheelSetSerializer


# ---------------------------------------------------------------------------
# EligibleCouponsListView
# ---------------------------------------------------------------------------

class AdminCouponsListView(BaseAppAdminAPIView):
    """
    GET /coupons/eligible/

    Returns all currently eligible *marketing* coupons (is_reward=False).
    Reward coupons are not listed here — they live in the user's wallet.

    Optional query param:
        ?scope=global|business
        ?business_id=<id>
        ?coupon_type=delivery|itemdiscount|...
        ?eligable=true
        ?reward=true|false|all
    """

    def get(self, request):
        qs = (
            Coupons.objects
            .all()
        )

        scope = request.query_params.get("scope")
        business_id = request.query_params.get("business_id")
        coupon_type = self.request.query_params.get("coupon_type")
        only_eligable = self.request.query_params.get("eligable", "false").lower()
        is_reward = (self.request.query_params.get("reward", "true").lower())

        if is_reward != "all":
            qs = qs.filter(is_reward=(is_reward=="true"))
        if only_eligable == "true":
            qs = qs.filter(eligible_coupon_q())
        if scope:
            qs = qs.filter(scope=scope)
        if business_id:
            qs = qs.filter(business_id=business_id)
        if coupon_type:
            qs = qs.filter(coupon_type=coupon_type)
        
        qs = qs.order_by("-created_at", "-valid_from")

        serializer = CouponSerializer(qs, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# CouponWheelGetView
# ---------------------------------------------------------------------------
# a way to check if the wheel is empty

class CouponWheelGetView(BaseCustomerAPIView):
    """
    GET /coupons/wheel/

    Returns the currently active wheel with its eligible reward coupons.
    Coupons that have been exhausted (uses_count >= max_uses) are already
    removed from the wheel by WheelService.award_coupon_to_user, so whatever
    is in wheel.coupons is safe to display.
    """

    def get(self, request):
        wheel = (
            CouponWheel.objects
            .filter(is_active=True)
            .prefetch_related(
                Prefetch(
                    "coupons",
                    queryset=Coupons.objects.filter(eligible_coupon_for_wheel_with_min_lifetime_q()),
                )
            )
            .first()
        )
        if not wheel:
            return Response(
                {"detail": "No active wheel at the moment."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CouponWheelSerializer(wheel)
        return Response(serializer.data)


class AdminCouponWheelListView(BaseAppAdminAPIView, generics.ListAPIView):
    """
    GET /coupons/wheel/

    Returns the currently active wheel with its eligible reward coupons.
    Coupons that have been exhausted (uses_count >= max_uses) are already
    removed from the wheel by WheelService.award_coupon_to_user, so whatever
    is in wheel.coupons is safe to display.
    """
    serializer_class = CouponWheelBaseSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = (
            CouponWheel.objects
            # .prefetch_related("coupons")
            .all()
        )

        # scope = self.request.query_params.get("scope")
        # if scope:
        #     qs = qs.filter(scope=scope)

        return qs


class AdminCouponWheelDetailView(BaseAppAdminAPIView, generics.RetrieveAPIView):
    queryset = CouponWheel.objects.prefetch_related("coupons")
    serializer_class = CouponWheelSerializer
    # lookup_field = "id"


# ---------------------------------------------------------------------------
# CouponWheelSpinView
# ---------------------------------------------------------------------------
# we need at add a permission like wheel chance

class CouponWheelSpinView(BaseCustomerAPIView):
    """
    POST /coupons/wheel/spin/

    Spins the wheel for the authenticated user:
      1. Loads the active wheel and its eligible reward coupons.
      2. Randomly selects one coupon from the wheel entries.
      3. Delegates to WheelService.award_coupon_to_user which:
         - Atomically increments uses_count on the coupon.
         - Removes the coupon from the wheel if it is now exhausted.
         - Creates a UserCouponWallet entry for the user.
      4. Returns the awarded wallet entry.

    If the wheel is empty (all coupons exhausted between load and spin)
    a 409 is returned — the client should refresh the wheel display.

    Body: none required.
    """

    def post(self, request):
        wheel = (
            CouponWheel.objects
            .filter(is_active=True)
            .prefetch_related(
                Prefetch(
                    "coupons",
                    # Only bring in coupons that are still eligible at spin time.
                    # This is a best-effort filter; WheelService does the atomic
                    # check so there is no race condition risk here.
                    queryset=Coupons.objects.filter(eligible_coupon_for_wheel_with_min_lifetime_q(3)),
                )
            )
            .first()
        )

        if not wheel:
            return Response(
                {"detail": "No active wheel at the moment."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Build the weighted entry list:
        # Each coupon fills exactly one slot in the list, so a uniform random
        # pick gives equal probability. If you ever want weighted odds, multiply
        # each coupon by a weight here.
        eligible_coupons = list(wheel.coupons.all())

        if not eligible_coupons:
            return Response(
                {"detail": "The wheel has no available prizes right now."},
                status=status.HTTP_409_CONFLICT,
            )

        chosen_coupon: Coupons = random.choice(eligible_coupons)

        wallet_entry = WheelService.award_coupon_to_user(
            coupon=chosen_coupon,
            user=request.user,
            from_spin=True,
        )

        if wallet_entry is None:
            # The chosen coupon was claimed by another concurrent spin.
            # Return the result anyway with a different coupon if any remain,
            # otherwise tell the client to retry.
            remaining = [c for c in eligible_coupons if c.pk != chosen_coupon.pk]
            if not remaining:
                return Response(
                    {"detail": "All prizes were just claimed. Please try again shortly."},
                    status=status.HTTP_409_CONFLICT,
                )

            # Try once more with another random coupon from the remaining list.
            fallback = random.choice(remaining)
            wallet_entry = WheelService.award_coupon_to_user(
                coupon=fallback,
                user=request.user,
                from_spin=True,
            )
            if wallet_entry is None:
                return Response(
                    {"detail": "All prizes were just claimed. Please try again shortly."},
                    status=status.HTTP_409_CONFLICT,
                )

        serializer = UserCouponWalletSerializer(wallet_entry)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# UserCouponWalletView
# ---------------------------------------------------------------------------

class UserCouponWalletListView(BaseCustomerAPIView, generics.ListAPIView):
    """
    GET /coupons/wallet/

    Returns the authenticated user's reward coupon wallet.

    Query params:
        ?unused=true
        ?search=code|description

    Each entry includes the full coupon details and an is_expired flag so
    the client can visually separate usable from expired entries without
    additional requests.
    """
    serializer_class = UserCouponWalletSerializer

    def get_queryset(self):
        qs = UserCouponWallet.objects.select_related("coupon").filter(
            user=self.request.user
        )

        only_unused = self.request.query_params.get("unused")
        if only_unused == "true":
            qs = qs.filter(is_used=False)
        
        search = self.request.query_params.get("search")

        if search:
            qs = qs.filter(
                Q(coupon__code__icontains=search) |
                Q(coupon__description__icontains=search)
            )

        return qs.order_by("-awarded_at")
