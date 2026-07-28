from decimal import Decimal
from rest_framework import serializers
from accounts.models import DriverAvailability
from driver_api.models import (
    SupportFAQCategory,
    SupportFAQItem,
)
from payments.models import LedgerEntry, Withdrawal
from support_center.models import SupportTicket, SupportTicketMessage
from phonenumber_field.serializerfields import PhoneNumberField  # type: ignore


class DriverDashboardSerializer(serializers.Serializer):
    profile = serializers.DictField()
    wallet = serializers.DictField()
    active_order = serializers.DictField(allow_null=True)
    unread_notifications = serializers.IntegerField()
    open_tickets = serializers.IntegerField()


class DriverProfileSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    gender = serializers.CharField(required=False, allow_blank=True)
    birth_date = serializers.DateField(required=False, allow_null=True)
    residential_address = serializers.CharField(required=False, allow_blank=True)
    phone_number = PhoneNumberField(required=False, allow_null=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    vehicle_make = serializers.CharField(required=False, allow_blank=True)
    vehicle_type = serializers.CharField(required=False, allow_blank=True)
    vehicle_number = serializers.CharField(required=False, allow_blank=True)


class AvailabilitySlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverAvailability
        fields = ["weekday", "time_mask"]


class DriverAvailabilityUpdateSerializer(serializers.Serializer):
    is_online = serializers.BooleanField(required=False)
    is_available = serializers.BooleanField(required=False)
    schedule = AvailabilitySlotSerializer(many=True, required=False)


class FAQCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportFAQCategory
        fields = ["id", "name", "sort_order"]


class FAQItemSerializer(serializers.ModelSerializer):
    category = FAQCategorySerializer()

    class Meta:
        model = SupportFAQItem
        fields = ["id", "question", "answer", "tags", "sort_order", "category"]


class TicketListSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = [
            "id",
            "category",
            "subject",
            "status",
            "priority",
            "is_blocking",
            "created_at",
            "closed_at",
        ]


class TicketCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = ["category", "subject", "description", "priority"]


class TicketDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = [
            "id",
            "category",
            "subject",
            "description",
            "status",
            "priority",
            "is_blocking",
            "created_at",
            "updated_at",
            "closed_at",
        ]


class TicketMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicketMessage
        fields = ["id", "sender_type", "sender_id", "message", "attachments_json", "created_at"]


class TicketMessageCreateSerializer(serializers.Serializer):
    message = serializers.CharField()
    attachments_json = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )


class WalletSerializer(serializers.Serializer):
    current_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    available_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    last_settled_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class EarningsSummarySerializer(serializers.Serializer):
    total_earned = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_withdrawn = serializers.DecimalField(max_digits=12, decimal_places=2)
    available_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    period_start = serializers.DateTimeField(allow_null=True)
    period_end = serializers.DateTimeField(allow_null=True)


class LedgerEntrySerializer(serializers.ModelSerializer):
    entry_type = serializers.CharField(source="type")
    amount = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    source_type = serializers.SerializerMethodField()
    source_id = serializers.SerializerMethodField()
    metadata = serializers.SerializerMethodField()

    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "entry_type",
            "amount",
            "status",
            "source_type",
            "source_id",
            "metadata",
            "created_at",
        ]

    def get_amount(self, obj):
        return Decimal(obj.amount or 0) / Decimal("100")

    def get_status(self, _obj):
        return "posted"

    def get_source_type(self, obj):
        return "sale" if obj.sale_id else "withdrawal"

    def get_source_id(self, obj):
        return str(obj.sale_id or "")

    def get_metadata(self, obj):
        return {"role": obj.role, "notes": obj.notes}


class WithdrawalEligibilitySerializer(serializers.Serializer):
    eligible = serializers.BooleanField()
    minimum_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    max_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    available_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    checks = serializers.DictField()


class WithdrawalRequestCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1.00"))


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    amount = serializers.SerializerMethodField()
    bank_snapshot = serializers.SerializerMethodField()
    review_snapshot = serializers.SerializerMethodField()
    transfer_ref = serializers.CharField(source="paystack_transfer_ref", allow_blank=True, allow_null=True)
    payment_withdrawal = serializers.SerializerMethodField()
    needs_manual_review = serializers.SerializerMethodField()
    approved_at = serializers.DateTimeField(source="requested_at")
    paid_at = serializers.DateTimeField(source="completed_at", allow_null=True)

    class Meta:
        model = Withdrawal
        fields = [
            "id",
            "amount",
            "status",
            "bank_snapshot",
            "idempotency_key",
            "review_snapshot",
            "transfer_ref",
            "payment_withdrawal",
            "failure_reason",
            "retry_count",
            "needs_manual_review",
            "created_at",
            "approved_at",
            "processed_at",
            "paid_at",
        ]

    def get_amount(self, obj):
        return Decimal(obj.amount or 0) / Decimal("100")

    def get_bank_snapshot(self, obj):
        return {"recipient_code": obj.paystack_recipient_code}

    def get_review_snapshot(self, obj):
        return {"strategy": obj.strategy}

    def get_payment_withdrawal(self, obj):
        return str(obj.id)

    def get_needs_manual_review(self, obj):
        return obj.status == "failed"


class AnalysisPerformanceQuerySerializer(serializers.Serializer):
    range = serializers.ChoiceField(choices=["7d", "30d", "90d", "custom"], required=False, default="30d")
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)
    granularity = serializers.ChoiceField(choices=["day", "week"], required=False, default="day")

    def validate(self, attrs):
        if attrs["range"] == "custom":
            if not attrs.get("from_date") or not attrs.get("to_date"):
                raise serializers.ValidationError("from_date and to_date are required when range=custom")
            if attrs["from_date"] > attrs["to_date"]:
                raise serializers.ValidationError("from_date cannot be after to_date")
        return attrs


