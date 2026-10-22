from rest_framework import serializers
from payments.models import Bank, Withdrawal, ResponsibleParty


class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = [
            "id",
            "country",
            "code",
            "name",
            "active",
        ]


class SaleInitializeSerializer(serializers.Serializer):
    business_owner_id = serializers.CharField(required=True)
    amount_kobo = serializers.IntegerField(required=True, min_value=1)
    driver_id = serializers.CharField(required=False, allow_null=True, default=None)
    metadata = serializers.DictField(required=False, default=dict)


class SaleRefundSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, default="Refund requested")
    responsible_party = serializers.ChoiceField(
        choices=ResponsibleParty.choices,
        default=ResponsibleParty.BUSINESS.value,
    )
    responsible_party_reason = serializers.CharField(required=False, allow_blank=True, default="")


class WalletBalanceQuerySerializer(serializers.Serializer):
    role = serializers.CharField(required=False, allow_null=True, default=None)


class RequestWithdrawalSerializer(serializers.Serializer):
    amount_kobo = serializers.IntegerField(required=True, min_value=1)
    strategy = serializers.ChoiceField(
        choices=["batch", "realtime"],
        required=False,
        default="batch",
    )
    role = serializers.CharField(required=False, allow_null=True, default=None)
    transaction_pin = serializers.CharField(required=False, allow_blank=True, default="")


class WithdrawalHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Withdrawal
        fields = [
            "id",
            "amount",
            "status",
            "strategy",
            "batch_date",
            "requested_at",
            "completed_at",
            "failure_reason",
        ]


class AdminReviewWithdrawalActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve_and_transfer", "mark_paid", "reject"])
    reason = serializers.CharField(required=False, default="Admin rejected withdrawal claim")
