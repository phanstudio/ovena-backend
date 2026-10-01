# referrals/views.py
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from django.core.exceptions import ValidationError as DjangoValidationError

from referrals.models import ProfileReferral
from referrals.constants import SUPPORTED_REFEREE_ROLES, ROLE_CUSTOMER
from referrals.serializers import (
    ApplyReferralCodeSerializer,
    MyReferralStatusSerializer,
    ReferralItemSerializer,
)
from referrals.services import (
    apply_referral_code,
    referral_stats,
)
from common.customer.view import BaseCustomerAPIView
from rest_framework.exceptions import NotFound


class ApplyReferralCodeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        s = ApplyReferralCodeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        vd = s.validated_data
        profile_type = vd.get("profile_type", ROLE_CUSTOMER)

        if profile_type not in SUPPORTED_REFEREE_ROLES:
            return Response(
                {"detail": "The referral program is currently only open to customers and drivers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if profile_type == ROLE_CUSTOMER:
            profile = getattr(request.user, "customer_profile", None)
        else:
            profile = getattr(request.user, "driver_profile", None)

        if not profile:
            return Response(
                {"detail": f"{profile_type.capitalize()} profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        device_id = request.headers.get("X-Device-ID") or vd.get("device_id") or None
        ip_address = request.META.get("REMOTE_ADDR") or None

        try:
            referral = apply_referral_code(
                user=request.user,
                profile=profile,
                code=vd["code"],
                role=profile_type,
                device_id=device_id,
                ip_address=ip_address,
            )
        except DjangoValidationError as e:
            msg = e.messages[0] if getattr(e, "messages", None) else str(e)
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "detail": "Referral code applied.",
                "referral_id": referral.id,
                "referrer_user_id": referral.referrer_user_id,
                "fraud_status": referral.fraud_status,
            },
            status=status.HTTP_201_CREATED,
        )


class MyReferralStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_profile(self, request):
        profile_type = request.query_params.get("profile_type", ROLE_CUSTOMER)
        if profile_type == ROLE_CUSTOMER:
            profile = getattr(request.user, "customer_profile", None)
        else:
            profile = getattr(request.user, "driver_profile", None)

        if not profile:
            raise NotFound(f"{profile_type.capitalize()} profile not found.")
        return profile

    def get(self, request):
        profile = self.get_profile(request)
        code = getattr(profile, "referral_code", "")

        stats = referral_stats(request.user)

        data = {
            "referral_code": code,
            "total_referrals": stats["total"],
            "successful_referrals": stats["successful"],
            "pending_referrals": stats["pending"],
        }
        return Response(MyReferralStatusSerializer(data).data)


class MyReferralsListView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ReferralItemSerializer

    def get_queryset(self):
        return (
            ProfileReferral.objects.filter(referrer_user=self.request.user)
            .select_related("referee_user")
            .order_by("-created_at")
        )


class CustomerMyReferralStatusView(MyReferralStatusView, BaseCustomerAPIView):
    def get_profile(self, request):
        return self.get_customer_profile(request)
