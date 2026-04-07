from phonenumber_field.serializerfields import PhoneNumberField  # type: ignore
from rest_framework import serializers
from accounts.models import User, BusinessAdmin

class AdminUpdateSerializer(serializers.Serializer):
    phone_number = PhoneNumberField(required=False, allow_null=True)
    full_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    def validate_email(self, value):
        if not value:
            return None

        user = self.context["request"].user

        if User.objects.exclude(pk=user.pk).filter(email=value).exists():
            raise serializers.ValidationError("Email already in use.")

        return value

    def validate_phone_number(self, value):
        if not value:
            return None

        user = self.context["request"].user

        if User.objects.exclude(pk=user.pk).filter(phone_number=value).exists():
            raise serializers.ValidationError("Phone number already in use.")

        return value

class BusinessMetricsQuerySerializer(serializers.Serializer):
    RANGE_CHOICES = ("today", "7d", "30d", "custom")
    range = serializers.ChoiceField(choices=RANGE_CHOICES, default="30d")
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)

    def validate(self, attrs):
        if attrs["range"] == "custom":
            if not attrs.get("from_date") or not attrs.get("to_date"):
                raise serializers.ValidationError("from_date and to_date are required when range=custom.")
            if attrs["from_date"] > attrs["to_date"]:
                raise serializers.ValidationError("from_date cannot be after to_date.")
        return attrs

class BusinessTransactionHistoryQuerySerializer(BusinessMetricsQuerySerializer):
    transaction_type = serializers.ChoiceField(
        choices=("all", "credit", "debit", "reversal", "withdrawal"),
        default="all",
        required=False,
    )
    withdrawal_status = serializers.CharField(required=False, allow_blank=True)
    
class AdminTransactionPinSerializer(serializers.Serializer):
    current_pin = serializers.CharField(required=False, allow_blank=True, min_length=4, max_length=4)
    pin = serializers.RegexField(regex=r"^\d{4}$")
    confirm_pin = serializers.RegexField(regex=r"^\d{4}$")

    def validate(self, attrs):
        if attrs["pin"] != attrs["confirm_pin"]:
            raise serializers.ValidationError("pin and confirm_pin must match.")

        business_admin: BusinessAdmin = self.context.get("business_admin")
        if business_admin and business_admin.has_transaction_pin and not attrs.get("current_pin"):
            raise serializers.ValidationError({"current_pin": "current_pin is required to update the transaction pin."})
        if business_admin and business_admin.has_transaction_pin and attrs.get("current_pin"):
            if not business_admin.check_transaction_pin(attrs["current_pin"]):
                raise serializers.ValidationError({"current_pin": "Invalid current pin."})
        return attrs

class BranchInputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField(max_length=200)
    address = serializers.CharField(max_length=500, required=False, default="")
    latitude = serializers.FloatField(required=False)
    longitude = serializers.FloatField(required=False)
    delivery_method = serializers.ChoiceField(
        choices=["instant", "scheduled"], default="instant"
    )
    pre_order_open_period = serializers.TimeField(required=False, allow_null=True)
    final_order_time = serializers.TimeField(required=False, allow_null=True)
    
    def validate(self, attrs):
        address = attrs.get("address")
        lat = attrs.get("latitude")
        lng = attrs.get("longitude")

        # If address given → require lat & long
        if address is not None:
            if (lat is None or lng is None):
                raise serializers.ValidationError(
                    "Latitude and longitude must be provided when address is set."
                )

        # Prevent partial coords
        if (lat is None) ^ (lng is None):
            raise serializers.ValidationError(
                "Both latitude and longitude must be provided together."
            )

        return attrs

class StaffRevokedSerializer(serializers.Serializer):
    agent_id = serializers.IntegerField()
    revoked = serializers.BooleanField()
