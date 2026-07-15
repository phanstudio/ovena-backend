"""
payments/points/models.py

Points ledger. Deliberately NOT the same table as payments.models.LedgerEntry --
points are not money, don't touch Paystack, and shouldn't share a hash/audit
trail with real NGN balances. The append-only + service-layer discipline is
copied from LedgerEntry/Withdrawal on purpose.
"""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from common.models.ulid import ULIDField


class PointsLedgerEntry(models.Model):
    """
    Immutable, append-only record of every point credit/debit.
    One row = one event. balance_after is a snapshot, same as LedgerEntry.
    """

    EVENT_REFERRAL_SUCCESS = "referral_success"
    EVENT_REFERRED_FIRST_ORDER = "referred_first_order"
    EVENT_ORDER_STREAK_5 = "order_streak_5"
    EVENT_ORDER_MILESTONE_5 = "order_milestone_5"
    EVENT_ORDER_RATED = "order_rated"
    EVENT_REDEMPTION = "redemption"
    EVENT_ADJUSTMENT = "adjustment"

    EVENT_CHOICES = [
        (EVENT_REFERRAL_SUCCESS, "Successful referral"),
        (EVENT_REFERRED_FIRST_ORDER, "Referred user's first order"),
        (EVENT_ORDER_STREAK_5, "5-order streak"),
        (EVENT_ORDER_MILESTONE_5, "5th order milestone (scratch card)"),
        (EVENT_ORDER_RATED, "Order rated"),
        (EVENT_REDEMPTION, "Points redeemed / withdrawn"),
        (EVENT_ADJUSTMENT, "Manual adjustment / reversal"),
    ]

    id = ULIDField(primary_key=True, editable=False, max_length=32)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="points_entries"
    )
    event_type = models.CharField(max_length=32, choices=EVENT_CHOICES)
    points = models.IntegerField()  # positive = credit, negative = debit
    balance_after = models.IntegerField()

    # The "cause" -- required before this row can ever be paid out. Points at
    # whatever justified the award: a Sale, a referred User, a Rating, etc.
    proof_content_type = models.ForeignKey(
        ContentType, on_delete=models.PROTECT, null=True, blank=True
    )
    proof_object_id = models.CharField(max_length=64, null=True, blank=True)
    proof = GenericForeignKey("proof_content_type", "proof_object_id")

    # Every write goes through the service layer with a deterministic key so
    # the same event (e.g. the same order hitting a webhook twice) can never
    # double-award.
    idempotency_key = models.CharField(max_length=150, unique=True)

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payments_points_ledger_entry"
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["event_type"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk and PointsLedgerEntry.objects.filter(pk=self.pk).exists():
            raise ValidationError("PointsLedgerEntry rows are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("PointsLedgerEntry rows cannot be deleted; write a reversal instead.")

    def __str__(self) -> str:
        return f"{self.event_type} {self.points:+d} - {self.user_id}"


class PointsEventRule(models.Model):
    """
    Configurable point values, one row per event type. Lets ops add/adjust
    rules (e.g. bump the referral bonus for a promo week) without a deploy.
    Flat rules set points_value; ranged rules (scratch card) set min/max
    instead and the actual amount is decided at award time by the caller.
    """

    event_type = models.CharField(
        max_length=32, choices=PointsLedgerEntry.EVENT_CHOICES, unique=True
    )
    points_value = models.PositiveIntegerField(null=True, blank=True)
    min_points = models.PositiveIntegerField(null=True, blank=True)
    max_points = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    description = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments_points_event_rule"

    def clean(self):
        has_flat = self.points_value is not None
        has_range = self.min_points is not None and self.max_points is not None
        if not has_flat and not has_range:
            raise ValidationError("Set either points_value, or both min_points and max_points.")
        if has_range and self.min_points > self.max_points:
            raise ValidationError("min_points cannot be greater than max_points.")

    def __str__(self) -> str:
        value = self.points_value if self.points_value is not None else f"{self.min_points}-{self.max_points}"
        return f"{self.event_type}: {value} ({'active' if self.is_active else 'inactive'})"


class PointsWithdrawalRequest(models.Model):
    """
    Mirrors Withdrawal's shape but stays entirely separate. Whether/how this
    ever converts to NGN (conversion rate, payout rail) isn't specified yet --
    treat this as the redemption record, not a payout trigger, until that's
    decided.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("paid", "Paid"),
    ]

    id = ULIDField(primary_key=True, editable=False, max_length=32)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="points_withdrawals"
    )
    points_requested = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    # The debit hold on the points ledger for this request.
    ledger_entry = models.OneToOneField(
        PointsLedgerEntry, on_delete=models.PROTECT, null=True, blank=True
    )

    requested_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"PointsWithdrawal {self.points_requested}pts - {self.user_id} [{self.status}]"


class MonthlyLeaderboardSnapshot(models.Model):
    """
    Frozen standings for one calendar month. Created once, by the finalize
    job, right after the month ends -- never recomputed after that, even if
    later reversals touch that month's ledger rows. The *current* month is
    never represented here; it's computed live (see service.get_live_leaderboard).
    """

    period_start = models.DateField(unique=True)  # always the 1st of the month
    period_end = models.DateField()
    finalized_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payments_points_leaderboard_snapshot"
        ordering = ["-period_start"]

    def __str__(self) -> str:
        return f"Leaderboard {self.period_start:%Y-%m}"


class MonthlyLeaderboardEntry(models.Model):
    """One user's frozen rank + points for a finalized month."""

    snapshot = models.ForeignKey(
        MonthlyLeaderboardSnapshot, on_delete=models.CASCADE, related_name="entries"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="leaderboard_entries"
    )
    points = models.IntegerField()
    rank = models.PositiveIntegerField()

    class Meta:
        db_table = "payments_points_leaderboard_entry"
        constraints = [
            models.UniqueConstraint(fields=["snapshot", "user"], name="uniq_leaderboard_snapshot_user"),
        ]
        ordering = ["rank"]

    def __str__(self) -> str:
        return f"#{self.rank} {self.user_id} - {self.points}pts ({self.snapshot.period_start:%Y-%m})"
