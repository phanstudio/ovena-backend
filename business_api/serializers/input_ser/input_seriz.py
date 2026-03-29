from rest_framework import serializers

class AdminUpdateSerializer(serializers.Serializer):
    phone_number = serializers.CharField(required=False, allow_blank=True)
    full_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)

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
