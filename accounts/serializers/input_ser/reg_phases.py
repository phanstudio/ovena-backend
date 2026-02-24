from rest_framework import serializers
import pycountry # type: ignore
    
class RestaurantPhase1Serializer(serializers.Serializer):
    business_name = serializers.CharField(max_length=255)
    business_type = serializers.CharField(max_length=100)
    country = serializers.CharField(max_length=100)
    business_address = serializers.CharField(max_length=500)
    email = serializers.EmailField()
    phone_number = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True)

    def validate_country(self, value): # ask if they can handel convertion themselves
        value = value.strip()

        # If ISO-2 code sent
        if len(value) == 2:
            c = pycountry.countries.get(alpha_2=value.upper())
            if c:
                return c.alpha_2
            raise serializers.ValidationError("Invalid country code")

        # If full name sent
        try:
            c = pycountry.countries.search_fuzzy(value)[0]
            return c.alpha_2
        except Exception:
            raise serializers.ValidationError("Invalid country")

class BranchOperatingHoursSerializer(serializers.Serializer):
    day = serializers.IntegerField(min_value=0, max_value=6)  # 0=Mon, 6=Sun
    open_time = serializers.TimeField()
    close_time = serializers.TimeField()
    is_closed = serializers.BooleanField(default=False)


class BranchInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    address = serializers.CharField(max_length=500, required=False, default="")
    latitude = serializers.FloatField(required=False)
    longitude = serializers.FloatField(required=False)
    delivery_method = serializers.ChoiceField(
        choices=["instant", "scheduled"], default="instant"
    )
    pre_order_open_period = serializers.TimeField(required=False, allow_null=True)
    final_order_time = serializers.TimeField(required=False, allow_null=True)
    operating_hours = BranchOperatingHoursSerializer(many=True, required=False, default=list)
    
    def validate(self, attrs):
        address = attrs.get("address")
        lat = attrs.get("latitude")
        lng = attrs.get("longitude")

        # If address given → require lat & long
        if address and (lat is None or lng is None):
            raise serializers.ValidationError(
                "Latitude and longitude must be provided when address is set."
            )

        # Prevent partial coords
        if (lat is None) ^ (lng is None):
            raise serializers.ValidationError(
                "Both latitude and longitude must be provided together."
            )

        return attrs

class RestaurantPaymentSerializer(serializers.Serializer):
    bank = serializers.CharField(max_length=200)
    account_number = serializers.CharField(max_length=20)
    account_name = serializers.CharField(max_length=200)
    bvn = serializers.CharField(max_length=20)


class RestaurantPhase2Serializer(serializers.Serializer):
    registered_business_name = serializers.CharField(max_length=255)
    business_type = serializers.CharField(max_length=100, required=False)
    tax_identification_number = serializers.CharField(max_length=100, required=False, default="")
    rc_number = serializers.CharField(max_length=100, required=False, default="")
    # files handled via request.FILES, not here
    payment = RestaurantPaymentSerializer(required=False)
    branches = BranchInputSerializer(many=True, required=False, default=list)

class RegisterBAdminSerializer(serializers.Serializer):
    full_name = serializers.CharField()
    phone_number = serializers.CharField()
    otp_code = serializers.CharField()
