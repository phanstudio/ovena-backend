# referrals/serializers.py
from rest_framework import serializers
from referrals.models import ProfileReferral

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
    referee_user_id = serializers.IntegerField(source="referee_user_id", read_only=True)

    class Meta:
        model = ProfileReferral
        fields = ["id", "created_at", "converted_at", "reward_issued", "referee_user_id"]
