from rest_framework import serializers
from accounts.models import (
    BusinessOnboardStatus,
    BusinessCerd,
    BusinessVerification,
    BusinessPayoutAccount,
    BusinessAdmin
)

# ──────────────────────────────────────────────
# DRIVER SERIALIZERS
# ──────────────────────────────────────────────

class NINVerificationSerializer(serializers.Serializer):
    nin = serializers.CharField(
        min_length=11,
        max_length=11,
        help_text="11-digit National Identification Number",
    )


class BVNVerificationSerializer(serializers.Serializer):
    bvn = serializers.CharField(
        min_length=11,
        max_length=11,
        help_text="11-digit Bank Verification Number",
    )


class BVNValidationSerializer(serializers.Serializer):
    bvn = serializers.CharField(min_length=11, max_length=11)
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    dob = serializers.DateField(required=False, help_text="Format: YYYY-MM-DD")


class AccountNumberSerializer(serializers.Serializer):
    account_number = serializers.CharField(
        min_length=10,
        max_length=10,
        help_text="10-digit NUBAN account number",
    )
    bank_code = serializers.CharField(
        max_length=10,
        help_text="CBN bank code e.g. '044' for Access Bank",
    )


class FaceMatchSerializer(serializers.Serializer):
    image = serializers.CharField(
        help_text="Base64-encoded JPEG or PNG selfie image",
    )
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    bvn = serializers.CharField(min_length=11, max_length=11, required=False)
    nin = serializers.CharField(min_length=11, max_length=11, required=False)

    def validate(self, attrs):
        if not attrs.get("bvn") and not attrs.get("nin"):
            raise serializers.ValidationError(
                "At least one of 'bvn' or 'nin' must be provided for face matching."
            )
        return attrs


class PlateNumberSerializer(serializers.Serializer):
    plate_number = serializers.CharField(
        help_text="Vehicle plate number e.g. 'ABC123XY'",
    )


# ──────────────────────────────────────────────
# BUSINESS SERIALIZERS
# ──────────────────────────────────────────────

class TINVerificationSerializer(serializers.Serializer):
    tin = serializers.CharField(
        help_text="Tax Identification Number from FIRS",
    )


class RCNumberSerializer(serializers.Serializer):
    rc_number = serializers.CharField(
        help_text="CAC Registration Number e.g. '1234567'",
    )


class BusinessBVNSerializer(serializers.Serializer):
    bvn = serializers.CharField(
        min_length=11,
        max_length=11,
        help_text="BVN of a business owner or director",
    )

class AdminBusinessReviewListSerializer(serializers.ModelSerializer):
    business_image = serializers.ImageField(source="business.business_image", read_only=True)
    business_logo = serializers.ImageField(source="business.business_logo", read_only=True)
    class Meta:
        model = BusinessAdmin
        fields = [
            "id", "name", "business_logo", "business_image", "cerd"
        ]


class BusinessVerificationSerializer(serializers.ModelSerializer):

    class Meta:
        model = BusinessVerification
        fields = [
            "id",
            "verification_type",
            "status",
            "provider_name",
            "provider_ref",
            "created_at",
            "completed_at",
        ]
        read_only_fields = [
            "id",
            "verification_type",
            "created_at",
            "completed_at",
        ]


class BusinessVerificationUpdateSerializer(serializers.ModelSerializer):

    verification_type = serializers.ChoiceField(
        choices=BusinessVerification.TYPE_CHOICES
    )

    class Meta:
        model = BusinessVerification
        fields = [
            "verification_type",
            "status",
            "provider_name",
            "provider_ref",
        ]


class BusinessCerdSerializer(serializers.ModelSerializer):

    class Meta:
        model = BusinessCerd
        fields = [
            "business_type",
            "doc_type",
            "business_doc",
            "registered_business_name",
            "tax_identification_number",
            "rc_number",
            "bn_number",
        ]


class BusinessPayoutAccountSerializer(serializers.ModelSerializer):

    class Meta:
        model = BusinessPayoutAccount
        fields = [
            "bank_name",
            "bank_account_name",
        ]


class AdminBusinessReviewDetailsSerializer(serializers.ModelSerializer):
    """
    Serializer used for GET.
    Returns the onboarding status, business CERD information,
    payout information and all verification records.
    """

    cerd = serializers.SerializerMethodField()
    verifications = serializers.SerializerMethodField()
    payout = serializers.SerializerMethodField()

    class Meta:
        model = BusinessOnboardStatus
        fields = [
            "id",
            "onboarding_step",
            "is_onboarding_complete",
            "needs_manual_review",
            "checked",
            "cerd",
            "verifications",
            "payout",
        ]

    def get_cerd(self, obj):
        business = obj.admin.business

        if not business:
            return None

        try:
            return BusinessCerdSerializer(
                business.cerd,
                context=self.context,
            ).data
        except BusinessCerd.DoesNotExist:
            return None

    def get_verifications(self, obj):
        business = obj.admin.business

        if not business:
            return []

        verifications = business.verifications.all()

        return BusinessVerificationSerializer(
            verifications,
            many=True,
            context=self.context,
        ).data

    def get_payout(self, obj):
        business = obj.admin.business

        if not business:
            return None

        try:
            return BusinessPayoutAccountSerializer(
                business.payout,
                context=self.context,
            ).data
        except BusinessPayoutAccount.DoesNotExist:
            return None


class AdminBusinessReviewUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer used for PATCH.

    Allows editing:
    - onboarding review fields
    - CERD information
    - payout information
    - verification statuses
    """

    verifications = BusinessVerificationUpdateSerializer(
        many=True,
        required=False,
    )

    class Meta:
        model = BusinessOnboardStatus
        fields = [
            "needs_manual_review",
            "checked",
            "verifications",
        ]

    def update(self, instance, validated_data):
        verifications_data = validated_data.pop("verifications", None)

        # Update onboarding status fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        business = instance.admin.business

        needs_review = validated_data.get("needs_manual_review", True)
        business.onboarding_complete = not needs_review
        business.save()

        if not business:
            return instance

        # Update verifications
        if verifications_data is not None:

            for verification_data in verifications_data:

                verification_type = verification_data.get(
                    "verification_type"
                )

                if not verification_type:
                    continue

                verification = BusinessVerification.objects.filter(
                    business=business,
                    verification_type=verification_type,
                ).first()

                if not verification:
                    continue

                # Only update allowed fields
                if "status" in verification_data:
                    verification.status = verification_data["status"]

                if "provider_name" in verification_data:
                    verification.provider_name = verification_data[
                        "provider_name"
                    ]

                if "provider_ref" in verification_data:
                    verification.provider_ref = verification_data[
                        "provider_ref"
                    ]

                verification.save()

        return instance
