"""
payments/points/serializers.py
"""

from rest_framework import serializers

from points import service
from points.models import PointsEventRule, PointsLedgerEntry, PointsWithdrawalRequest


class PointsBalanceSerializer(serializers.Serializer):
    """
    One row of 'individuals and their points'. Not a ModelSerializer since
    the balance is an annotation/aggregate, not a field on User.
    """

    user_id = serializers.CharField()
    name = serializers.CharField(allow_blank=True)
    points_balance = serializers.IntegerField()


class PointsLedgerEntrySerializer(serializers.ModelSerializer):
    """Read-only feed of what earned/spent points -- the 'proof' trail."""

    proof_type = serializers.SerializerMethodField()

    class Meta:
        model = PointsLedgerEntry
        fields = [
            "id",
            "event_type",
            "points",
            "balance_after",
            "proof_type",
            "proof_object_id",
            "notes",
            "created_at",
        ]
        read_only_fields = fields

    def get_proof_type(self, obj):
        return obj.proof_content_type.model if obj.proof_content_type_id else None


class PointsWithdrawalRequestSerializer(serializers.ModelSerializer):
    """Read representation, used for both the requester's own list and admin review."""

    class Meta:
        model = PointsWithdrawalRequest
        fields = ["id", "user", "points_requested", "status", "requested_at", "resolved_at"]
        read_only_fields = fields


class PointsWithdrawalRequestCreateSerializer(serializers.Serializer):
    """Input shape for POST /points/withdrawals/."""

    points_requested = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.CharField(max_length=150)

    def validate_points_requested(self, value):
        if value < service.MINIMUM_WITHDRAWAL_POINTS:
            raise serializers.ValidationError(
                f"Minimum withdrawal is {service.MINIMUM_WITHDRAWAL_POINTS} points."
            )
        return value


class PointsWithdrawalResolveSerializer(serializers.Serializer):
    """Input shape for PATCH /points/withdrawals/<id>/resolve/."""

    status = serializers.ChoiceField(choices=[c for c, _ in PointsWithdrawalRequest.STATUS_CHOICES])


class LeaderboardEntrySerializer(serializers.Serializer):
    """Shared shape for both live (current month) and snapshot (past month) rows."""

    rank = serializers.IntegerField()
    user_id = serializers.CharField()
    name = serializers.CharField(allow_blank=True)
    points = serializers.IntegerField()


class MyLeaderboardRankSerializer(serializers.Serializer):
    user_id = serializers.CharField()
    points = serializers.IntegerField()
    rank = serializers.IntegerField(allow_null=True)


class LeaderboardPeriodSerializer(serializers.Serializer):
    period = serializers.DateField()


class PointsEventRuleSerializer(serializers.ModelSerializer):
    """Admin CRUD of point values -- the 'more rules coming' lever."""

    class Meta:
        model = PointsEventRule
        fields = [
            "id",
            "event_type",
            "points_value",
            "min_points",
            "max_points",
            "is_active",
            "description",
            "updated_at",
        ]

    def validate(self, attrs):
        points_value = attrs.get("points_value", getattr(self.instance, "points_value", None))
        min_points = attrs.get("min_points", getattr(self.instance, "min_points", None))
        max_points = attrs.get("max_points", getattr(self.instance, "max_points", None))

        has_flat = points_value is not None
        has_range = min_points is not None and max_points is not None
        if not has_flat and not has_range:
            raise serializers.ValidationError(
                "Set either points_value, or both min_points and max_points."
            )
        if has_range and min_points > max_points:
            raise serializers.ValidationError("min_points cannot be greater than max_points.")
        return attrs
