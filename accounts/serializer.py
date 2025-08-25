from rest_framework import serializers
from .models import (
    CustomerProfile,
    DriverProfile,
    Restaurant
)

class CustomerProfileSerializer(serializers.ModelSerializer):
    age = serializers.ReadOnlyField()  # uses the @property
    
    class Meta:
        model = CustomerProfile
        fields = ["id", "location", "birth_date", "age"]

class DriverProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverProfile
        fields = ["id", "nin", "driver_license", "plate_number", "vehicle_type", "photo"]

class RestaurantProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Restaurant
        fields = ["id", "company_name", "certification", "bn_number"]
