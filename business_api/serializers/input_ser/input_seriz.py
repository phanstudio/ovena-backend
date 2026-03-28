from rest_framework import serializers

class AdminUpdateSerializer(serializers.Serializer):
    phone_number = serializers.CharField(required=False, allow_blank=True)
    # "first_name": "string",
    # "last_name": "string",
    full_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)
