import hashlib
import os
import uuid
from django.core.exceptions import ValidationError
from django.db import models
from accounts.models import User
from authflow.services.model import ULIDField


class UserAccount(models.Model):
    """
    Payment-specific extension of the core accounts.User model.

    Holds provider-specific payout details so we don't have to put
    Paystack/bank fields directly on the main User table.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="payment_account")
    paystack_recipient_code = models.CharField(max_length=100, blank=True)
    bank_account_number = models.CharField(max_length=20, blank=True)
    bank_code = models.CharField(max_length=10, blank=True)
    bank_account_name = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.bank_account_name} ({self.bank_code})"


class PlatformConfig(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get(cls, key, default=None):
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    def __str__(self):
        return f"{self.key} = {self.value}"

    class Meta:
        verbose_name_plural = "Platform Configs"


class PaymentIdempotencyKey(models.Model):
    scope = models.CharField(max_length=64)
    actor_id = models.CharField(max_length=64)
    key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    response_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["scope", "actor_id", "key"], name="uniq_payment_idempotency_scope_actor_key"),
        ]


class Sale(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("in_escrow", "In Escrow"),
        ("completed", "Completed"),
        ("refunded", "Refunded"),
        ("disputed", "Disputed"),
    ]

    # id = ULIDField(primary_key=True, editable=False)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=100, unique=True)
    paystack_reference = models.CharField(max_length=100, unique=True, null=True, blank=True)
    paystack_access_code = models.CharField(max_length=100, blank=True)

    payer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="purchases")
    driver = models.ForeignKey(User, on_delete=models.PROTECT, related_name="driven_sales", null=True, blank=True)
    business_owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="business_sales")
    referral_user = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="referral_sales", null=True, blank=True)

    total_amount = models.BigIntegerField()
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="pending")
    split_snapshot = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)

    service_completed_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    refund_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Sale {self.reference} - NGN {self.total_amount / 100:.2f}"


class LedgerEntry(models.Model):
    ROLES = [
        ("driver", "Driver"),
        ("business_owner", "Business Owner"),
        ("referral", "Referral"),
        ("platform", "Platform"),
    ]
    TYPES = [
        ("credit", "Credit"),
        ("debit", "Debit"),
        ("reversal", "Reversal"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="ledger_entries")
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="ledger_entries", null=True, blank=True)
    role = models.CharField(max_length=50, choices=ROLES)
    type = models.CharField(max_length=50, choices=TYPES)
    amount = models.BigIntegerField()
    balance_after = models.BigIntegerField()
    row_hash = models.CharField(max_length=64)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk and LedgerEntry.objects.filter(pk=self.pk).exists():
            raise ValidationError("LedgerEntry rows are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("LedgerEntry rows cannot be deleted.")

    def verify_hash(self):
        return self.row_hash == LedgerEntry.generate_hash(
            sale_id=str(self.sale_id) if self.sale_id else "withdrawal",
            user_id=str(self.user_id),
            amount=self.amount,
            entry_type=self.type,
            role=self.role,
            created_at=self.created_at.isoformat(),
        )

    @staticmethod
    def generate_hash(sale_id, user_id, amount, entry_type, role, created_at):
        salt = os.environ.get("LEDGER_HASH_SALT", "")
        if not salt:
            raise ValueError("LEDGER_HASH_SALT env variable not set")
        payload = f"{sale_id}|{user_id}|{amount}|{entry_type}|{role}|{created_at}|{salt}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def __str__(self):
        return f"{self.type} NGN {abs(self.amount)/100:.2f} - {self.user} ({self.role})"


class Withdrawal(models.Model):
    STATUS_CHOICES = [
        ("pending_batch", "Pending Batch"),
        ("processing", "Processing"),
        ("complete", "Complete"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]
    STRATEGY_BATCH = "batch"
    STRATEGY_REALTIME = "realtime"
    STRATEGY_CHOICES = [
        (STRATEGY_BATCH, "Batch"),
        (STRATEGY_REALTIME, "Realtime"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="withdrawals")
    amount = models.BigIntegerField()
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="pending_batch")
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES, default=STRATEGY_BATCH)

    idempotency_key = models.CharField(max_length=128, blank=True)

    batch_date = models.DateField(null=True, blank=True)
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)

    paystack_transfer_code = models.CharField(max_length=100, blank=True)
    paystack_transfer_ref = models.CharField(max_length=100, unique=True, null=True, blank=True)
    paystack_recipient_code = models.CharField(max_length=100)

    ledger_entry = models.OneToOneField(LedgerEntry, on_delete=models.PROTECT, null=True, blank=True)
    failure_reason = models.TextField(blank=True)

    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "idempotency_key"], condition=~models.Q(idempotency_key=""), name="uniq_withdrawal_user_idem"),
        ]

    def __str__(self):
        return f"Withdrawal NGN {self.amount/100:.2f} - {self.user} [{self.status}]"


class PaystackWebhookLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=100)
    event_id = models.CharField(max_length=100, blank=True)
    event_hash = models.CharField(max_length=64, db_index=True)
    paystack_reference = models.CharField(max_length=100, blank=True)
    payload = models.JSONField()
    signature_valid = models.BooleanField(default=False)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_reason = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk and PaystackWebhookLog.objects.filter(pk=self.pk).exists():
            original = PaystackWebhookLog.objects.get(pk=self.pk)
            immutable_fields = ["event_type", "event_id", "event_hash", "paystack_reference", "payload", "signature_valid", "received_at"]
            for field in immutable_fields:
                if getattr(original, field) != getattr(self, field):
                    raise ValidationError("Webhook payload fields are immutable after insert.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("WebhookLog rows cannot be deleted.")

    class Meta:
        verbose_name = "Paystack Webhook Log"
        constraints = [
            models.UniqueConstraint(fields=["event_hash"], name="uniq_paystack_event_hash"),
            models.UniqueConstraint(fields=["event_id"], condition=~models.Q(event_id=""), name="uniq_paystack_event_id"),
        ]


class ReconciliationLog(models.Model):
    STATUS_CHOICES = [
        ("clean", "Clean"),
        ("mismatches_found", "Mismatches Found"),
        ("error", "Error"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run_date = models.DateField()
    status = models.CharField(max_length=50, choices=STATUS_CHOICES)
    total_checked = models.IntegerField(default=0)
    mismatches = models.IntegerField(default=0)
    mismatch_details = models.JSONField(default=list)
    error_message = models.TextField(blank=True)
    ran_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reconciliation {self.run_date} - {self.status}"

