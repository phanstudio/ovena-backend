# referrals/views.py
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from django.core.exceptions import ValidationError as DjangoValidationError

from referrals.models import ProfileReferral
from referrals.serializers import (
    ApplyReferralCodeSerializer,
    MyReferralStatusSerializer,
    ReferralItemSerializer,
)
from referrals.services import (
    apply_referral_code,
    referral_count,
    successful_referrals,
    ensure_profile_base,
)


class ApplyReferralCodeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        s = ApplyReferralCodeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        vd = s.validated_data
        profile_type = vd.get("profile_type", "customer")

        if profile_type == "customer":
            profile = getattr(request.user, "customer_profile", None)
        else:
            profile = getattr(request.user, "driver_profile", None)

        if not profile:
            return Response(
                {"detail": f"{profile_type.capitalize()} profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            referral = apply_referral_code(profile=profile, code=vd["code"])
        except DjangoValidationError as e:
            # e.message may be a string; e.messages may be list
            msg = e.messages[0] if getattr(e, "messages", None) else str(e)
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "detail": "Referral code applied.",
                "referral_id": referral.id,
                "referrer_user_id": referral.referrer_user_id,
            },
            status=status.HTTP_201_CREATED,
        )


class MyReferralStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile_type = request.query_params.get("profile_type", "customer")
        if profile_type == "customer":
            profile = getattr(request.user, "customer_profile", None)
        else:
            profile = getattr(request.user, "driver_profile", None)

        if not profile:
            return Response(
                {"detail": f"{profile_type.capitalize()} profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        base_profile = ensure_profile_base(profile)
        code = base_profile.referral_code

        total = referral_count(profile)
        successful = successful_referrals(profile)
        pending = total - successful

        data = {
            "referral_code": code,
            "total_referrals": total,
            "successful_referrals": successful,
            "pending_referrals": pending,
        }
        return Response(MyReferralStatusSerializer(data).data)


class MyReferralsListView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ReferralItemSerializer

    def get_queryset(self):
        return ProfileReferral.objects.filter(referrer_user=self.request.user).order_by("-created_at")
