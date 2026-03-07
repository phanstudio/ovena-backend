from rest_framework import serializers
from django.contrib.auth import get_user_model

# from accounts.models import (
#     DriverProfile, DriverCred, DriverAvailability,
#     DriverDocument, DriverBankAccount, DriverOnboardingSubmission,
# )

User = get_user_model()

COMPLIANCE_QUESTIONS = [
    "have_you_worked_as_delivery_rider",
    "how_long_worked_as_rider",        # conditional on above
    "familiarity_with_local_routes",
    "have_used_gps_for_deliveries",
    "can_handle_cash_on_delivery",
    "willing_to_follow_traffic_rules",
    "willing_to_wear_helmet_and_gear",
    "punctuality_self_rating",
    "has_health_condition",
    "health_condition_details",        # conditional on above
    "why_work_with_us",
    "how_soon_can_you_start",
]


# ─── Phase 1 ──────────────────────────────────────────────────────────────────

class OnboardingPhase1InputSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    phone_number = serializers.CharField(max_length=18)
    password = serializers.CharField()
    email = serializers.EmailField()
    gender = serializers.ChoiceField(choices=["male", "female", "other", "na"])
    birth_date = serializers.DateField()
    residential_address = serializers.CharField()

    # Next of kin (stored in DriverCred)
    next_of_kin_name = serializers.CharField(max_length=160)
    next_of_kin_phone = serializers.CharField(max_length=18)
    next_of_kin_address = serializers.CharField()  # stored in answers
    referre_code = serializers.CharField(required=False, allow_blank=True, max_length=20)

    def validate_phone_number(self, value):
        qs = User.objects.filter(phone_number=value)
        if self.context.get("driver_user_id"):
            qs = qs.exclude(pk=self.context["driver_user_id"])
        if qs.exists():
            raise serializers.ValidationError("A driver with this phone number already exists.")
        return value

    def validate_email(self, value):
        qs = User.objects.filter(email=value)
        if self.context.get("driver_user_id"):
            qs = qs.exclude(pk=self.context["driver_user_id"])
        if qs.exists():
            raise serializers.ValidationError("A driver with this email already exists.")
        return value


class OnboardingPhase1OutputSerializer(serializers.Serializer):
    phase = serializers.IntegerField(default=1)
    status = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    phone_number = serializers.CharField()
    email = serializers.EmailField()
    gender = serializers.CharField()
    birth_date = serializers.DateField()
    residential_address = serializers.CharField()
    next_of_kin_name = serializers.CharField()
    next_of_kin_phone = serializers.CharField()
    next_of_kin_address = serializers.CharField()


# ─── Phase 2 ──────────────────────────────────────────────────────────────────

class OnboardingPhase2InputSerializer(serializers.Serializer):
    drivers_license = serializers.ImageField()
    nin = serializers.CharField(min_length=11, max_length=11)
    bvn = serializers.CharField(min_length=11, max_length=11)
    vehicle_type = serializers.CharField(max_length=50)
    vehicle_make = serializers.CharField(max_length=60)
    plate_number = serializers.CharField(max_length=50)
    guarantor1_name = serializers.CharField(max_length=160)
    guarantor1_phone = serializers.CharField(max_length=18)
    guarantor2_name = serializers.CharField(max_length=160)
    guarantor2_phone = serializers.CharField(max_length=18)

    def validate_nin(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("NIN must be 11 digits.")
        return value

    def validate_bvn(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("BVN must be 11 digits.")
        return value


class OnboardingPhase2OutputSerializer(serializers.Serializer):
    phase = serializers.IntegerField(default=2)
    status = serializers.CharField()
    drivers_license_url = serializers.CharField()
    nin_last4 = serializers.CharField()
    bvn_last4 = serializers.CharField()
    nin_verification_status = serializers.CharField()
    bvn_verification_status = serializers.CharField()
    vehicle_type = serializers.CharField()
    vehicle_make = serializers.CharField()
    plate_number = serializers.CharField()
    guarantor1_name = serializers.CharField()
    guarantor1_phone = serializers.CharField()
    guarantor2_name = serializers.CharField()
    guarantor2_phone = serializers.CharField()


# ─── Phase 3 ──────────────────────────────────────────────────────────────────

class AvailabilitySlotSerializer(serializers.Serializer):
    weekday = serializers.IntegerField(min_value=0, max_value=6)
    time_mask = serializers.IntegerField(min_value=0, max_value=15)


class OnboardingPhase3InputSerializer(serializers.Serializer):
    availability = AvailabilitySlotSerializer(many=True)
    compliance_answers = serializers.DictField(child=serializers.CharField(allow_blank=True))
    delivery_bag = serializers.ImageField()

    def validate_compliance_answers(self, value):
        # required = [
        #     "have_you_worked_as_delivery_rider",
        #     "familiarity_with_local_routes",
        #     "have_used_gps_for_deliveries",
        #     "can_handle_cash_on_delivery",
        #     "willing_to_follow_traffic_rules",
        #     "willing_to_wear_helmet_and_gear",
        #     "punctuality_self_rating",
        #     "has_health_condition",
        #     "why_work_with_us",
        #     "how_soon_can_you_start",
        # ]
        required= COMPLIANCE_QUESTIONS
        missing = [q for q in required if q not in value]
        if missing:
            raise serializers.ValidationError(f"Missing required answers: {missing}")

        # Conditional: if worked as rider → duration required
        if value.get("have_you_worked_as_delivery_rider", "").lower() in ("yes", "true", "1"):
            if not value.get("how_long_worked_as_rider", "").strip():
                raise serializers.ValidationError(
                    {"how_long_worked_as_rider": "Required when 'have_you_worked_as_delivery_rider' is Yes."}
                )

        # Conditional: if has health condition → details required
        if value.get("has_health_condition", "").lower() in ("yes", "true", "1"):
            if not value.get("health_condition_details", "").strip():
                raise serializers.ValidationError(
                    {"health_condition_details": "Required when 'has_health_condition' is Yes."}
                )

        return value

    def validate_availability(self, value):
        if not value:
            raise serializers.ValidationError("At least one availability slot is required.")
        weekdays = [slot["weekday"] for slot in value]
        if len(weekdays) != len(set(weekdays)):
            raise serializers.ValidationError("Duplicate weekday entries are not allowed.")
        return value


class OnboardingPhase3OutputSerializer(serializers.Serializer):
    phase = serializers.IntegerField(default=3)
    status = serializers.CharField()
    availability = AvailabilitySlotSerializer(many=True)
    compliance_answers = serializers.DictField()
    delivery_bag_url = serializers.CharField()


# ─── Phase 4 ──────────────────────────────────────────────────────────────────

class OnboardingPhase4InputSerializer(serializers.Serializer):
    bank_name = serializers.CharField(max_length=120)
    account_number = serializers.CharField(min_length=10, max_length=10)
    account_name = serializers.CharField(max_length=160)
    verified_selfie = serializers.ImageField()

    def validate_account_number(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Account number must be 10 digits.")
        return value


class OnboardingPhase4OutputSerializer(serializers.Serializer):
    phase = serializers.IntegerField(default=4)
    status = serializers.CharField()
    bank_name = serializers.CharField()
    account_number = serializers.CharField()
    account_name = serializers.CharField()
    bank_verification_status = serializers.CharField()
    selfie_url = serializers.CharField()
    onboarding_complete = serializers.BooleanField()


# ─── Status / Progress ────────────────────────────────────────────────────────

class OnboardingStatusOutputSerializer(serializers.Serializer):
    current_phase = serializers.IntegerField()
    phases_complete = serializers.ListField(child=serializers.IntegerField())
    all_phases_complete = serializers.BooleanField()
    submission_status = serializers.CharField()  # draft / submitted / approved / rejected
    reviewer_note = serializers.CharField(allow_blank=True)
    phase_data = serializers.DictField()
