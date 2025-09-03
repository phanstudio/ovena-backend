from rest_framework import serializers
from .models import (
    CustomerProfile,
    DriverProfile,
    Restaurant,
    User,
    Address
)
from django.db import transaction

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

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "phone_number", "name")

class OAuthCodeSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=("google", "apple"))
    code = serializers.CharField()
    code_verifier = serializers.CharField(required=False, allow_null=True, allow_blank=True)

class RegisterCustomerSerializer(serializers.Serializer):
    phone_number = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    lat = serializers.FloatField(required=False)
    long = serializers.FloatField(required=False)
    birth_date = serializers.DateField(required=False)
    name = serializers.CharField(required=False, allow_blank=True)
    referre_code = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        email = data.get("email")
        phone = data.get("phone_number")
        if not email and not phone:
            raise serializers.ValidationError("Either email or phone number is required.")

        if email:
            user = User.objects.filter(email=email).first()
        elif phone:
            user = User.objects.filter(phone_number=phone).first()
        else:
            raise serializers.ValidationError("User not found. Complete OTP verification first.")

        data["user"] = user
        referre_code = data.get("referre_code")
        if referre_code:
            data["referred_by"] = CustomerProfile.objects.filter(referre_code=referre_code).first()
        return data

    @transaction.atomic
    def create(self, validated_data):
        user = validated_data["user"]
        name = validated_data.get("name")
        birth_date = validated_data.get("birth_date")
        lat = validated_data.get("lat")
        long = validated_data.get("long")
        referred_by = validated_data.get("referred_by", None)

        if name:
            user.name = name
            user.save(update_fields=["name"])
        location = Address.objects.create(
            address="unknown",
            latitude=lat,
            longitude=long,
        )
        profile, created = CustomerProfile.objects.get_or_create(
            user=user,
            defaults={
                "birth_date": birth_date,
                "default_address": location,
                "referred_by": referred_by,
            },
        )

        if not created:
            updates = {}
            if birth_date:
                updates["birth_date"] = birth_date
            if location:
                updates["default_address"] = location
            if referred_by:
                updates["referred_by"] = referred_by
            if updates:
                for field, value in updates.items():
                    setattr(profile, field, value)
                profile.save(update_fields=list(updates.keys()))
        profile.addresses.add(location)
        return profile


