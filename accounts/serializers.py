from rest_framework import serializers
from .models import (
    CustomerProfile,
    DriverProfile,
    Restaurant,
    User,
    Address
)
from django.db import transaction
from django.contrib.gis.geos import Point

class CustomerProfileSerializer(serializers.ModelSerializer):
    age = serializers.ReadOnlyField()  # uses the @property
    
    class Meta:
        model = CustomerProfile
        fields = [
            "id", 
            "default_address", "addresses",
            "birth_date", "age"
        ]

class DriverProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverProfile
        fields = ["id", 
                #   "nin", "driver_license", "plate_number", "vehicle_type", "photo"
        ]

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
    code_verifier = serializers.CharField(required=False, allow_null=True, allow_blank=True) # remove

# class RegisterCustomerSerializer(serializers.Serializer):
#     phone_number = serializers.CharField(required=False, allow_blank=True)
#     email = serializers.EmailField(required=False, allow_blank=True)
#     lat = serializers.FloatField(required=False)
#     long = serializers.FloatField(required=False)
#     birth_date = serializers.DateField(required=False)
#     name = serializers.CharField(required=False, allow_blank=True)
#     referre_code = serializers.CharField(required=False, allow_blank=True)

#     def validate(self, data):
#         email = data.get("email")
#         phone = data.get("phone_number")

#         if not email and not phone:
#             raise serializers.ValidationError(
#                 "Either email or phone number is required."
#             )

#         if email:
#             user = User.objects.filter(email=email).first()
#         else:
#             user = User.objects.filter(phone_number=phone).first()

#         if not user:
#             raise serializers.ValidationError(
#                 "User not found. Complete OTP verification first."
#             )

#         # if CustomerProfile.objects.filter(user=user).exists(): # might be unnessary
#         #     raise serializers.ValidationError(
#         #         "Customer profile already exists for this user."
#         #     )

#         data["user"] = user

#         referre_code = data.get("referre_code")
#         if referre_code:
#             data["referred_by"] = CustomerProfile.objects.filter(
#                 referral_code=referre_code
#             ).first()

#         return data

#     @transaction.atomic
#     def create(self, validated_data):
#         user = validated_data["user"]
#         name = validated_data.get("name")
#         birth_date = validated_data.get("birth_date")
#         lat = validated_data.get("lat")
#         long = validated_data.get("long")
#         referred_by = validated_data.get("referred_by", None)

#         if name:
#             user.name = name
#             user.save(update_fields=["name"])

#         location = None
#         if lat is not None and long is not None:
#             location = Address.objects.create(
#                 address="unknown",
#                 location=Point(long, lat, srid=4326)
#             )
        
#         profile, created = CustomerProfile.objects.get_or_create(
#             user=user,
#             defaults={
#                 "birth_date": birth_date,
#                 "default_address": location,
#                 "referred_by": referred_by,
#             },
#         )

#         if not created:
#             updates = {}
#             if birth_date:
#                 updates["birth_date"] = birth_date
#             if location:
#                 updates["default_address"] = location
#             if referred_by:
#                 updates["referred_by"] = referred_by
#             if updates:
#                 for field, value in updates.items():
#                     setattr(profile, field, value)
#                 profile.save(update_fields=list(updates.keys()))
#         profile.addresses.add(location)
#         return profile

# class CreateCustomerSerializer(serializers.Serializer):
#     name = serializers.CharField(required=False, allow_blank=True)
#     email = serializers.EmailField(required=False, allow_blank=True)
#     phone_number = serializers.CharField(required=False, allow_blank=True)

#     lat = serializers.FloatField(required=False)
#     long = serializers.FloatField(required=False)
#     birth_date = serializers.DateField(required=False)
#     referre_code = serializers.CharField(required=False, allow_blank=True)

#     def validate(self, data):
#         user = self.context["user"]

#         if CustomerProfile.objects.filter(user=user).exists():
#             raise serializers.ValidationError(
#                 "Customer profile already exists."
#             )

#         # ─── EMAIL RULE ─────────────────────
#         email = data.get("email")
#         if email:
#             if user.email:
#                 raise serializers.ValidationError(
#                     {"email": "The user already has an email."}
#                 )
#             if User.objects.filter(email=email).exists():
#                 raise serializers.ValidationError(
#                     {"email": "This email is already in use."}
#                 )

#         # ─── PHONE RULE ─────────────────────
#         phone = data.get("phone_number")
#         if phone:
#             if user.phone_number:
#                 raise serializers.ValidationError(
#                     {"phone_number": "The user already has a phone number."}
#                 )
#             if User.objects.filter(phone_number=phone).exists():
#                 raise serializers.ValidationError(
#                     {"phone_number": "This phone number is already in use."}
#                 )

#         # referral
#         referre_code = data.get("referre_code")
#         if referre_code:
#             data["referred_by"] = CustomerProfile.objects.filter(
#                 referral_code=referre_code
#             ).first()

#         return data

#     @transaction.atomic
#     def create(self, validated_data):
#         user = self.context["user"]

#         # ─── USER FIELDS ─────────────────────
#         update_fields = []

#         if validated_data.get("name"):
#             user.name = validated_data["name"]
#             update_fields.append("name")

#         if validated_data.get("email"):
#             user.email = validated_data["email"]
#             update_fields.append("email")

#         if validated_data.get("phone_number"):
#             user.phone_number = validated_data["phone_number"]
#             update_fields.append("phone_number")

#         if update_fields:
#             user.save(update_fields=update_fields)

#         # ─── ADDRESS ─────────────────────
#         location = None
#         lat = validated_data.get("lat")
#         long = validated_data.get("long")

#         if lat is not None and long is not None:
#             location = Address.objects.create(
#                 address="unknown",
#                 location=Point(long, lat, srid=4326),
#             )

#         profile = CustomerProfile.objects.create(
#             user=user,
#             birth_date=validated_data.get("birth_date"),
#             default_address=location,
#             referred_by=validated_data.get("referred_by"),
#         )

#         if location:
#             profile.addresses.add(location)

#         return profile

class CreateCustomerSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    lat = serializers.FloatField(required=False)
    long = serializers.FloatField(required=False)
    birth_date = serializers.DateField(required=False)
    referre_code = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        user = self.context["user"]

        # thanks to CustomCustomerAuth
        if hasattr(user, "customer_profile"):
            raise serializers.ValidationError(
                "Customer profile already exists."
            )

        # identity fill rules
        if data.get("email"):
            if user.email:
                raise serializers.ValidationError(
                    {"email": "User already has an email."}
                )
            if User.objects.filter(email=data["email"]).exists():
                raise serializers.ValidationError(
                    {"email": "Email already in use."}
                )

        if data.get("phone_number"):
            if user.phone_number:
                raise serializers.ValidationError(
                    {"phone_number": "User already has a phone number."}
                )
            if User.objects.filter(phone_number=data["phone_number"]).exists():
                raise serializers.ValidationError(
                    {"phone_number": "Phone number already in use."}
                )

        referre_code = data.get("referre_code")
        if referre_code:
            data["referred_by"] = CustomerProfile.objects.filter(
                referral_code=referre_code
            ).first()

        return data
    
    @transaction.atomic
    def create(self, validated_data):
        user = self.context["user"]

        update_fields = []

        for field in ("name", "email", "phone_number"):
            if validated_data.get(field):
                setattr(user, field, validated_data[field])
                update_fields.append(field)

        if update_fields:
            user.save(update_fields=update_fields)

        location = None
        if validated_data.get("lat") is not None and validated_data.get("long") is not None:
            location = Address.objects.create(
                address="unknown",
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
            referred_by=validated_data.get("referred_by"),
        )

        if location:
            profile.addresses.add(location)

        return profile

# class UpdateCustomerSerializer(serializers.Serializer):
#     name = serializers.CharField(required=False, allow_blank=True)
#     email = serializers.EmailField(required=False, allow_blank=True)
#     phone_number = serializers.CharField(required=False, allow_blank=True)

#     lat = serializers.FloatField(required=False)
#     long = serializers.FloatField(required=False)
#     birth_date = serializers.DateField(required=False)

#     def validate(self, data):
#         user = self.context["user"]

#         # EMAIL
#         email = data.get("email")
#         if email:
#             if User.objects.exclude(id=user.id).filter(email=email).exists():
#                 raise serializers.ValidationError(
#                     {"email": "This email is already in use."}
#                 )

#         # PHONE
#         phone = data.get("phone_number")
#         if phone:
#             if User.objects.exclude(id=user.id).filter(phone_number=phone).exists():
#                 raise serializers.ValidationError(
#                     {"phone_number": "This phone number is already in use."}
#                 )

#         return data

#     @transaction.atomic
#     def update(self, instance, validated_data):
#         user = self.context["user"]

#         user_updates = []

#         if validated_data.get("name"):
#             user.name = validated_data["name"]
#             user_updates.append("name")

#         if validated_data.get("email"):
#             user.email = validated_data["email"]
#             user_updates.append("email")

#         if validated_data.get("phone_number"):
#             user.phone_number = validated_data["phone_number"]
#             user_updates.append("phone_number")

#         if user_updates:
#             user.save(update_fields=user_updates)

#         # profile updates
#         profile_updates = {}

#         if validated_data.get("birth_date"):
#             profile_updates["birth_date"] = validated_data["birth_date"]

#         lat = validated_data.get("lat")
#         long = validated_data.get("long")
#         if lat is not None and long is not None:
#             location = Address.objects.create(
#                 address="unknown",
#                 location=Point(long, lat, srid=4326),
#             )
#             profile_updates["default_address"] = location
#             instance.addresses.add(location)

#         if profile_updates:
#             for field, value in profile_updates.items():
#                 setattr(instance, field, value)
#             instance.save(update_fields=list(profile_updates.keys()))

#         return instance

class UpdateCustomerSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)

    lat = serializers.FloatField(required=False)
    long = serializers.FloatField(required=False)
    birth_date = serializers.DateField(required=False)

    def validate(self, data):
        user = self.context["user"]

        if not hasattr(user, "customer_profile"):
            raise serializers.ValidationError(
                "Customer profile does not exist."
            )

        if data.get("email"):
            if User.objects.exclude(id=user.id).filter(email=data["email"]).exists():
                raise serializers.ValidationError(
                    {"email": "This email is already in use."}
                )

        if data.get("phone_number"):
            if User.objects.exclude(id=user.id).filter(
                phone_number=data["phone_number"]
            ).exists():
                raise serializers.ValidationError(
                    {"phone_number": "This phone number is already in use."}
                )

        return data

    @transaction.atomic
    def update(self, instance, validated_data):
        user = self.context["user"]

        # ─── USER UPDATES ─────────────────────
        user_fields = []

        if validated_data.get("name"):
            user.name = validated_data["name"]
            user_fields.append("name")

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


from google.oauth2 import id_token
from google.auth.transport import requests
from rest_framework import serializers
from django.conf import settings

class GoogleAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField()

    def validate(self, data):
        try:
            client_id = settings.OAUTH_PROVIDERS.get("google").get("CLIENT_ID")
            info = id_token.verify_oauth2_token(
                data['id_token'],
                requests.Request(),
                client_id
            )
        except Exception as e:
            raise serializers.ValidationError(f"Invalid Google token: {e}")

        data['email'] = info['email']
        data['sub'] = info['sub']
        data['info'] = info
        return data

