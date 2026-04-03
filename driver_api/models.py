from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class DriverWallet(models.Model):
    driver = models.OneToOneField(
        "accounts.DriverProfile",
        on_delete=models.CASCADE,
        related_name="wallet",
    )
    current_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    available_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    pending_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    last_settled_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet(driver={self.driver_id}, available={self.available_balance})"


class DriverLedgerEntry(models.Model):
    TYPE_CREDIT = "credit"
    TYPE_DEBIT = "debit"
    TYPE_HOLD = "hold"
    TYPE_RELEASE = "release"
    TYPE_CHOICES = [
        (TYPE_CREDIT, "Credit"),
        (TYPE_DEBIT, "Debit"),
        (TYPE_HOLD, "Hold"),
        (TYPE_RELEASE, "Release"),
    ]

    STATUS_POSTED = "posted"
    STATUS_PENDING = "pending"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_POSTED, "Posted"),
        (STATUS_PENDING, "Pending"),
        (STATUS_FAILED, "Failed"),
    ]

    driver = models.ForeignKey("accounts.DriverProfile", on_delete=models.CASCADE, related_name="ledger_entries")
    entry_type = models.CharField(max_length=12, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    source_type = models.CharField(max_length=50, blank=True, default="")
    source_id = models.CharField(max_length=100, blank=True, default="")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_POSTED)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["driver", "-created_at"]),
            models.Index(fields=["source_type", "source_id"]),
        ]

    def __str__(self):
        return f"{self.driver_id} {self.entry_type} {self.amount}"


class DriverWithdrawalRequest(models.Model):
    STATUS_REQUESTED = "requested"
    STATUS_AUTO_REJECTED = "auto_rejected"
    STATUS_APPROVED = "approved"
    STATUS_PROCESSING = "processing"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_REQUESTED, "Requested"),
        (STATUS_AUTO_REJECTED, "Auto Rejected"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    driver = models.ForeignKey("accounts.DriverProfile", on_delete=models.CASCADE, related_name="withdrawals")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_REQUESTED)
    bank_snapshot = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=128)
    review_snapshot = models.JSONField(default=dict, blank=True)
    transfer_ref = models.CharField(max_length=120, blank=True, default="")
    payment_withdrawal = models.OneToOneField("payments.Withdrawal", on_delete=models.SET_NULL, null=True, blank=True, related_name="driver_withdrawal")
    failure_reason = models.TextField(blank=True, default="")
    retry_count = models.PositiveSmallIntegerField(default=0)
    needs_manual_review = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["driver", "idempotency_key"],
                name="uniq_driver_withdrawal_idempotency",
            )
        ]
        indexes = [models.Index(fields=["driver", "status", "-created_at"])]

    def mark_failed(self, reason: str, manual: bool = False):
        self.status = self.STATUS_FAILED
        self.failure_reason = reason
        self.needs_manual_review = manual
        self.processed_at = timezone.now()
        self.save(update_fields=["status", "failure_reason", "needs_manual_review", "processed_at", "updated_at"])


class SupportFAQCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class SupportFAQItem(models.Model):
    category = models.ForeignKey(SupportFAQCategory, on_delete=models.CASCADE, related_name="faqs")
    question = models.CharField(max_length=255)
    answer = models.TextField()
    tags = models.JSONField(default=list, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category__sort_order", "sort_order", "id"]
