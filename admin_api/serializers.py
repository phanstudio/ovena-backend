from rest_framework import serializers
from phonenumber_field.serializerfields import PhoneNumberField
from accounts.models import User
from admin_api.models import AppAdmin
from django.db import transaction

# class UserInfoSerializer(serializers.Serializer):
#     id = serializers.IntegerField()
#     name = serializers.CharField()

# class RegisterBAdminResponseSerializer(serializers.Serializer):
#     message = serializers.CharField()
#     refresh = serializers.CharField()
#     access = serializers.CharField()
#     user = UserInfoSerializer()

# class OnboardResponseSerializer(serializers.Serializer):
#     onboarding_step = serializers.IntegerField()
#     is_onboarding_complete = serializers.BooleanField()

class LoginResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    refresh = serializers.CharField()
    access = serializers.CharField()


class AppAdminLoginSerializer(serializers.Serializer):
    phone_number = PhoneNumberField()
    password = serializers.CharField()

class DriverDashboardSerializer(serializers.Serializer):
    profile = serializers.DictField()
    wallet = serializers.DictField()
    active_order = serializers.DictField(allow_null=True)
    unread_notifications = serializers.IntegerField()
    open_tickets = serializers.IntegerField()

class UserSerializer(serializers.ModelSerializer):
    phone_number = PhoneNumberField()

    class Meta:
        model = User
        fields = ["id", "email", "phone_number", "name"]
    
class AppAdminProfileSerializer(serializers.ModelSerializer):

    class Meta:
        model = AppAdmin
        fields = ["id"]

class UpdateAppAdminSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone_number = PhoneNumberField(required=False, allow_blank=True)

    # app admin
    device_name = serializers.FloatField(required=False)

    def validate(self, data):
        user = self.context["user"]

        if not hasattr(user, "app_admin"):
            raise serializers.ValidationError(
                "App Admin does not exist."
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

        if validated_data.get("device_name"):
            profile_updates["name"] = validated_data["device_name"]

        if profile_updates:
            for field, value in profile_updates.items():
                setattr(instance, field, value)
            instance.save(update_fields=list(profile_updates.keys()))

        return instance
