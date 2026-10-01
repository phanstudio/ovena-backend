from rest_framework import serializers
from referrals.models import ProfileReferral, ReferralPayout, MODE_CHOICES
from referrals.constants import REFERRAL_ROLE_CHOICES, ROLE_CUSTOMER, ROLE_DRIVER


class ApplyReferralCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20)
    profile_type = serializers.ChoiceField(
        choices=("customer", "driver"),
        required=False,
        default="customer",
    )
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")


class MyReferralStatusSerializer(serializers.Serializer):
    referral_code = serializers.CharField()
    total_referrals = serializers.IntegerField()
    successful_referrals = serializers.IntegerField()
    pending_referrals = serializers.IntegerField()


class ReferralItemSerializer(serializers.ModelSerializer):
    referee_user_id = serializers.IntegerField(
        source="referee_user.id",
        read_only=True,
    )
    referee_user_name = serializers.SerializerMethodField()
    role = serializers.CharField(source="referee_role", read_only=True)

    class Meta:
        model = ProfileReferral
        fields = [
            "id",
            "created_at",
            "converted_at",
            "is_consumed",
            "referee_user_id",
            "referee_user_name",
            "role",
            "fraud_status",
        ]

    def get_referee_user_name(self, obj):
        user = obj.referee_user
        if not user:
            return None
        if obj.referee_role == ROLE_CUSTOMER:
            cp = getattr(user, "customer_profile", None)
            return getattr(cp, "name", None) or str(user)
        elif obj.referee_role == ROLE_DRIVER:
            dp = getattr(user, "driver_profile", None)
            return getattr(dp, "full_name", None) or str(user)
        return str(user)


class ReferralPayoutSerializer(serializers.ModelSerializer):
    referrals_used = serializers.IntegerField(read_only=True)

    class Meta:
        model = ReferralPayout
        fields = [
            "id",
            "user",
            "units_paid",
            "conversion_rate",
            "referrals_used",
            "amount",
            "created_at",
        ]


class AdminReferralPaymentSerializer(serializers.Serializer):
    user_id = serializers.CharField()
    units = serializers.IntegerField(required=False, allow_null=True)
