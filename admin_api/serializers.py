from rest_framework import serializers
from phonenumber_field.serializerfields import PhoneNumberField
from accounts.models import User
from admin_api.models import AppAdmin
from django.db import transaction
from accounts.models import DriverProfile, Business
from payments.models import Withdrawal

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


class AdminUserListSerializer(serializers.ModelSerializer):
    phone_number = PhoneNumberField()
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "phone_number", "name", "is_active", "is_staff", "roles"]

    def get_roles(self, obj):
        # Uses the derived roles system (profiles + legacy fallback).
        try:
            return sorted(list(obj.derived_roles))
        except Exception:
            return []


class AdminDriverListSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    latest_onboarding_status = serializers.CharField(read_only=True, allow_blank=True, default="")
    latest_onboarding_submitted_at = serializers.DateTimeField(read_only=True, allow_null=True, default=None)
    pending_documents_count = serializers.IntegerField(read_only=True, default=0)
    pending_onboarding_submissions_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = DriverProfile
        fields = [
            "id",
            "user",
            "first_name",
            "last_name",
            "gender",
            "is_online",
            "is_available",
            "last_location_update",
            "vehicle_make",
            "vehicle_type",
            "vehicle_number",
            "total_deliveries",
            "avg_rating",
            "created_at",
            "latest_onboarding_status",
            "latest_onboarding_submitted_at",
            "pending_documents_count",
            "pending_onboarding_submissions_count",
        ]


class AdminBusinessListSerializer(serializers.ModelSerializer):
    admin_user = serializers.SerializerMethodField()
    branches_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Business
        fields = [
            "id",
            "business_name",
            "business_type",
            "country",
            "business_address",
            "email",
            "phone_number",
            "onboarding_complete",
            "created_at",
            "branches_count",
            "admin_user",
        ]

    def get_admin_user(self, obj):
        try:
            admin = obj.admin
        except Exception:
            return None
        if not admin or not getattr(admin, "user", None):
            return None
        return UserSerializer(admin.user).data


class AdminBusinessUpdateSerializer(serializers.Serializer):
    onboarding_complete = serializers.BooleanField(required=False)


class AdminWithdrawalSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    amount_ngn = serializers.SerializerMethodField()
    ledger_role = serializers.SerializerMethodField()

    class Meta:
        model = Withdrawal
        fields = [
            "id",
            "user",
            "amount",
            "amount_ngn",
            "status",
            "strategy",
            "idempotency_key",
            "batch_date",
            "retry_count",
            "max_retries",
            "paystack_transfer_code",
            "paystack_transfer_ref",
            "paystack_recipient_code",
            "ledger_role",
            "failure_reason",
            "requested_at",
            "processed_at",
            "completed_at",
        ]

    def get_amount_ngn(self, obj):
        try:
            return obj.amount / 100
        except Exception:
            return None

    def get_ledger_role(self, obj):
        try:
            if obj.ledger_entry_id and obj.ledger_entry:
                return obj.ledger_entry.role
        except Exception:
            pass
        return ""


class AdminWithdrawalMarkFailedSerializer(serializers.Serializer):
    reason = serializers.CharField()


class AdminSendNotificationSerializer(serializers.Serializer):
    # Either supply user_id (single user), or audience (broadcast segment).
    user_id = serializers.IntegerField(required=False)
    audience = serializers.ChoiceField(
        choices=("all", "customers", "drivers", "business_admins"),
        required=False,
    )

    notification_type = serializers.CharField(required=False, allow_blank=True, default="system")
    title = serializers.CharField()
    body = serializers.CharField()
    payload_json = serializers.JSONField(required=False)

    def validate(self, attrs):
        if not attrs.get("user_id") and not attrs.get("audience"):
            raise serializers.ValidationError("Provide either user_id or audience.")
        if attrs.get("user_id") and attrs.get("audience"):
            raise serializers.ValidationError("Provide only one of user_id or audience.")
        return attrs
