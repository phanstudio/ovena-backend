from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from authflow.services.model import AbstractBaseModel
from referrals.constants import (
    REFERRAL_ROLE_CHOICES,
    ROLE_CUSTOMER,
    FRAUD_STATUS_CHOICES,
    FRAUD_STATUS_CLEAN,
)

MODE_CHOICES = ["partial", "all"]

class ProfileReferral(AbstractBaseModel):

    referrer_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile_referrals_made",
    )
    referee_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile_referral_received",
    )

    # Role attribution (Customer or Driver)
    referrer_role = models.CharField(
        max_length=20,
        choices=REFERRAL_ROLE_CHOICES,
        default=ROLE_CUSTOMER,
        db_index=True,
    )
    referee_role = models.CharField(
        max_length=20,
        choices=REFERRAL_ROLE_CHOICES,
        default=ROLE_CUSTOMER,
        db_index=True,
    )

    # Anti-cheat audit fields
    referee_device_id = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        db_index=True,
    )
    referee_ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        db_index=True,
    )
    fraud_status = models.CharField(
        max_length=20,
        choices=FRAUD_STATUS_CHOICES,
        default=FRAUD_STATUS_CLEAN,
        db_index=True,
    )
    fraud_reason = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    converted_at = models.DateTimeField(null=True, blank=True)

    # 🔥 payout tracking
    is_consumed = models.BooleanField(default=False)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=~Q(referrer_user=F("referee_user")),
                name="chk_profile_referral_no_self_user",
            ),
        ]
        indexes = [
            models.Index(fields=["referrer_user", "converted_at"]),
            models.Index(fields=["is_consumed"]),
            models.Index(fields=["fraud_status"]),
        ]
    
    def clean(self):
        if self.referrer_user_id and self.referee_user_id:
            if self.referrer_user_id == self.referee_user_id:
                raise ValidationError("Self-referrals are not permitted.")

class ReferralPayout(AbstractBaseModel):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="referral_payouts"
    )

    units_paid = models.IntegerField()
    conversion_rate = models.IntegerField(default=10)

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    # 🔥 lean snapshot
    referral_snapshot = models.JSONField(default=list, blank=True)

    # 🔒 integrity
    snapshot_hash = models.CharField(max_length=64, blank=True)

    @property
    def referrals_used(self):
        return self.units_paid * self.conversion_rate

    def __str__(self):
        return f"Payout({self.user_id}) units={self.units_paid}"
