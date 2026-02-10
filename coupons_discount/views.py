from django.db.models import F
from rest_framework import generics, permissions
from .models import Coupons, CouponWheel
from .serializers import CouponSerializer, CouponWheelSerializer
from .services import eligible_coupon_q
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
import random
from django.db import transaction

# coupons/views.py
from rest_framework import generics, permissions
from .models import Coupons
from .serializers import CouponCreateUpdateSerializer

# time left should be added everywhere
# change if needed, the cred

class EligibleCouponsListView(generics.ListAPIView):
    """
    GET /api/coupons/eligible/
    Returns coupons that can be added / shown (not exhausted, active, valid).
    Optional filters:
      ?scope=global|restaurant
      ?restaurant_id=123
      ?coupon_type=delivery|itemdiscount|...
    """
    serializer_class = CouponSerializer
    permission_classes = [permissions.IsAdminUser] 

    def get_queryset(self):
        qs = Coupons.objects.filter(eligible_coupon_q()).select_related("restaurant", "category", "item")

        scope = self.request.query_params.get("scope")
        if scope:
            qs = qs.filter(scope=scope)

        restaurant_id = self.request.query_params.get("restaurant_id")
        if restaurant_id:
            qs = qs.filter(restaurant_id=restaurant_id)

        coupon_type = self.request.query_params.get("coupon_type")
        if coupon_type:
            qs = qs.filter(coupon_type=coupon_type)

        return qs.order_by("-valid_from", "code")

class CouponWheelGetView(APIView):
    """
    GET /api/coupon-wheel/
    Shows the active wheel (if any) and the eligible coupon options.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        wheel = CouponWheel.objects.filter(is_active=True).first()
        if not wheel:
            return Response({"detail": "No active coupon wheel."}, status=status.HTTP_404_NOT_FOUND)

        eligible = wheel.coupons.filter(eligible_coupon_q()).distinct()
        data = {
            "wheel_id": wheel.id,
            "max_entries_amount": wheel.max_entries_amount,
            "options": CouponSerializer(eligible, many=True).data,
        }
        return Response(data)

class CouponWheelSpinView(APIView):
    """
    POST /api/coupon-wheel/spin/
    Picks a random eligible coupon from the active wheel.
    If no eligible coupons remain => 409.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        wheel = CouponWheel.objects.filter(is_active=True).first()
        if not wheel:
            return Response({"detail": "No active coupon wheel."}, status=status.HTTP_404_NOT_FOUND)

        for _ in range(3):
            eligible_qs = wheel.coupons.filter(eligible_coupon_q()).distinct()

            count = eligible_qs.count()
            if count == 0:
                return Response(
                    {"detail": "No eligible coupons left on the wheel."},
                    status=status.HTTP_409_CONFLICT,
                )

            # Efficient random pick without pulling all rows:
            idx = random.randint(0, count - 1)
            picked = eligible_qs.order_by("id")[idx]  # stable order, then index

            # If you want spinning to "consume" a use (optional):
            # This is concurrency-safe and won't exceed max_uses.
            with transaction.atomic():
                updated = (
                    Coupons.objects
                    .filter(pk=picked.pk)
                    .filter(eligible_coupon_q())  # re-check at DB time
                    .update(uses_count=F("uses_count") + 1)
                )
                if updated == 0:
                    continue
                picked.refresh_from_db()

            return Response({"picked": CouponSerializer(picked).data})

        return Response({"detail": "Coupon just exhausted. Spin again."}, status=409)

class CouponWheelAdminView(generics.RetrieveAPIView):
    queryset = CouponWheel.objects.prefetch_related("coupons")
    serializer_class = CouponWheelSerializer

class CouponCreateView(generics.CreateAPIView):
    """
    POST /api/admin/coupons/
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = CouponCreateUpdateSerializer
    queryset = Coupons.objects.all()

class CouponUpdateView(generics.UpdateAPIView):
    """
    PATCH/PUT /api/admin/coupons/<id>/
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = CouponCreateUpdateSerializer
    queryset = Coupons.objects.all()


# coupons/views.py
from django.db import transaction
from rest_framework import generics, permissions
from .models import CouponWheel
from .serializers import CouponWheelSetSerializer

class CouponWheelSetterView(generics.UpdateAPIView):
    """
    PATCH /api/admin/coupon-wheels/<id>/
    Body can include:
      - max_entries_amount
      - coupon_ids: [1,2,3]
      - is_active: true/false  (if true, will deactivate other wheels)
    """
    permission_classes = [permissions.IsAdminUser]
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

class CouponWheelCreateView(generics.CreateAPIView):
    """
    POST /api/admin/coupon-wheels/
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = CouponWheelSetSerializer
    queryset = CouponWheel.objects.all()
