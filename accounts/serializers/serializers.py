from django.db import transaction
from django.contrib.gis.geos import Point
# from google.oauth2 import id_token  # type: ignore
# from google.auth.transport import requests  # type: ignore
# from django.conf import settings
from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from ..models import (
    CustomerProfile,
    DriverProfile,
    Business,
    User,
    Address,
    BusinessAdmin,
    PrimaryAgent, Branch
)
from referrals.services import apply_referral_code
from phonenumber_field.serializerfields import PhoneNumberField  # type: ignore
from points.tasks import award_referral_success_task


class AddressSerializer(serializers.ModelSerializer):
    # optional: return lat/lon as simple numbers
    lat = serializers.SerializerMethodField()
    long = serializers.SerializerMethodField()

    class Meta:
        model = Address
        fields = [
            "id", "label", "address", 
            "lat", "long", 
            "created_at"
        ]

    def get_lat(self, obj):
        return obj.location.y if obj.location else None  # y = latitude

    def get_long(self, obj):
        return obj.location.x if obj.location else None  # x = longitude


class CustomerProfileSerializer(serializers.ModelSerializer):
    age = serializers.ReadOnlyField()  # uses the @property
    default_address = AddressSerializer(read_only=True)
    addresses = AddressSerializer(many=True, read_only=True)

    class Meta:
        model = CustomerProfile
        fields = [
            "id",
            "default_address",
            "addresses",
            "birth_date",
            "age",
            "referral_code",
            "name",
            "pickup_food"
        ]


class DriverProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverProfile
        fields = [
            "id",
            "first_name",
            "last_name",
            "vehicle_number",
            "vehicle_type",
            "gender",
            "birth_date",
            "residential_address",
            "vehicle_make",
            "referral_code",
        ]


class BuisnessAdminProfileSerializer(serializers.ModelSerializer):
    business_image = serializers.ImageField(source="business.business_image", read_only=True)
    business_logo = serializers.ImageField(source="business.business_logo", read_only=True)
    class Meta:
        model = BusinessAdmin
        fields = [
            "id", "name", "business_logo", "business_image"
        ]


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = "__all__"


class PrimaryAgentProfileSerializer(serializers.ModelSerializer):
    is_active = serializers.SerializerMethodField()
    branch = BranchSerializer(read_only=True)

    class Meta:
        model = PrimaryAgent
        fields = [
            "id",
            "device_name",
            "is_active",
            "revoked",
            "created_at",
            "branch",
            "name",
        ]
        read_only_fields = fields

    def get_is_active(self, obj):
        return not obj.revoked


class RestaurantProfileSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="business_name", read_only=True)

    class Meta:
        model = Business
        fields = [
            "id",
            "business_name",
            "company_name",
            "business_type",
            "certification",
            "bn_number",
        ]


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "phone_number")


class OAuthCodeSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=("google", "apple"))
    id_token = serializers.CharField()


class Delete2Serializer(serializers.Serializer):
    user_id = serializers.IntegerField()


class CreateCustomerSerializer(serializers.Serializer):
    name = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True)
    phone_number = PhoneNumberField(required=False, allow_null=True)
    lat = serializers.FloatField(required=False)
    long = serializers.FloatField(required=False)
    birth_date = serializers.DateField(required=False)
    referral_code = serializers.CharField(required=False, allow_blank=True, default="")
    profile_pic = serializers.CharField(
        required=False, allow_blank=True
    )
    address = serializers.CharField(required=False, allow_blank=True, default="unknown")
    is_picking_up_food = serializers.BooleanField(required=False, default=False)

    def validate(self, data):
        user = self.context["user"]

        if user.customer_profile:
            raise serializers.ValidationError("Customer profile already exists.")

        # identity fill rules
        if data.get("email"):
            if user.email:
                raise serializers.ValidationError(
                    {"email": "User already has an email."}
                )
            if User.objects.filter(email=data["email"]).exists():
                raise serializers.ValidationError({"email": "Email already in use."})

        if data.get("phone_number"):
            if user.phone_number:
                raise serializers.ValidationError(
                    {"phone_number": "User already has a phone number."}
                )
            if User.objects.filter(phone_number=data["phone_number"]).exists():
                raise serializers.ValidationError(
                    {"phone_number": "Phone number already in use."}
                )

        return data

    @transaction.atomic
    def create(self, validated_data):
        user = self.context["user"]

        update_fields = []

        for field in ("email", "phone_number"):
            if validated_data.get(field):
                setattr(user, field, validated_data[field])
                update_fields.append(field)

        if update_fields:
            user.save(update_fields=update_fields)

        location = None
        if (
            validated_data.get("lat") is not None
            and validated_data.get("long") is not None
        ):
            location = Address.objects.create(
                address= validated_data["address"],
                location=Point(
                    validated_data["long"],
                    validated_data["lat"],
                    srid=4326,
                ),
            )

        profile = CustomerProfile.objects.create(
            user=user,
            birth_date=validated_data.get("birth_date"),
            default_address=location,
            name=validated_data["name"],
            pickup_food=validated_data["is_picking_up_food"],
        )

        if location:
            profile.addresses.add(location)

        referral_code = validated_data.get("referral_code")
        if referral_code:
            try:
                referral = apply_referral_code(profile=profile, code=referral_code)
                idempotency_key = f"referral-success:{referral.id}:{profile}"
                award_referral_success_task.delay(
                    referrer_id= referral.referrer_user.id, referred_user_id= referral.referee_user.id, 
                    idempotency_key= idempotency_key
                )
            except DjangoValidationError as exc:
                msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
                print(msg)
                raise serializers.ValidationError({"referral_code": msg})

        return profile


class UpdateCustomerSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone_number = PhoneNumberField(required=False, allow_blank=True)

    lat = serializers.FloatField(required=False)
    long = serializers.FloatField(required=False)
    birth_date = serializers.DateField(required=False)
    profile_pic = serializers.CharField(
        required=False, allow_blank=True
    )

    def validate(self, data):
        user = self.context["user"]

        if not user.customer_profile:
            raise serializers.ValidationError("Customer profile does not exist.")

        if data.get("email"):
            if User.objects.exclude(id=user.id).filter(email=data["email"]).exists():
                raise serializers.ValidationError(
                    {"email": "This email is already in use."}
                )

        if data.get("phone_number"):
            if (
                User.objects.exclude(id=user.id)
                .filter(phone_number=data["phone_number"])
                .exists()
            ):
                raise serializers.ValidationError(
                    {"phone_number": "This phone number is already in use."}
                )

        return data

    @transaction.atomic
    def update(self, instance, validated_data):
        user = self.context["user"]

        # ─── USER UPDATES ─────────────────────
        user_fields = []

        if validated_data.get("email"):
            user.email = validated_data["email"]
            user_fields.append("email")

        if validated_data.get("phone_number"):
            user.phone_number = validated_data["phone_number"]
            user_fields.append("phone_number")

        if user_fields:
            user.save(update_fields=user_fields)

        # ─── PROFILE UPDATES ──────────────────
        profile_updates = {}

        if validated_data.get("birth_date"):
            profile_updates["birth_date"] = validated_data["birth_date"]
        
        if validated_data.get("name"):
            profile_updates["name"] = validated_data["name"]

        lat = validated_data.get("lat")
        long = validated_data.get("long")

        if lat is not None and long is not None:
            location = Address.objects.create(
                address="unknown",
                location=Point(long, lat, srid=4326),
            )
            profile_updates["default_address"] = location
            instance.addresses.add(location)

        if profile_updates:
            for field, value in profile_updates.items():
                setattr(instance, field, value)
            instance.save(update_fields=list(profile_updates.keys()))

        return instance


# Oath
# class GoogleAuthSerializer(serializers.Serializer):
#     id_token = serializers.CharField()

#     def validate(self, data):
#         try:
#             client_id = settings.OAUTH_PROVIDERS.get("google").get("CLIENT_ID")
#             info = id_token.verify_oauth2_token(
#                 data["id_token"], requests.Request(), client_id
#             )
#         except Exception as e:
#             raise serializers.ValidationError(f"Invalid Google token: {e}")

#         data["email"] = info["email"]
#         data["sub"] = info["sub"]
#         data["info"] = info
#         return data
