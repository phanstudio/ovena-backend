from rest_framework import serializers


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
