from rest_framework import serializers
from referrals.models import ProfileReferral, ReferralPayout, MODE_CHOICES


class ApplyReferralCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20)
    profile_type = serializers.ChoiceField(
        choices=("customer", "driver"),
        required=False,
        default="customer",
    )

class MyReferralStatusSerializer(serializers.Serializer):
    referral_code = serializers.CharField()
    total_referrals = serializers.IntegerField()
    successful_referrals = serializers.IntegerField()
    pending_referrals = serializers.IntegerField()

class ReferralItemSerializer(serializers.ModelSerializer):
    # referee_user_id = serializers.IntegerField(source="referee_user_id", read_only=True)
    referee_user_id = serializers.IntegerField()

    class Meta:
        model = ProfileReferral
        fields = ["id", "created_at", "converted_at", "is_consumed", "referee_user_id"]

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
    mode = serializers.ChoiceField(choices=MODE_CHOICES)
