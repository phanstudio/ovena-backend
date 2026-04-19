from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from authflow.services.model import AbstractBaseModel

MODE_CHOICES = ["partial", "all"]

class ProfileReferral(AbstractBaseModel):
    referrer_profile = models.ForeignKey(
        "accounts.ProfileBase",
        on_delete=models.CASCADE,
        related_name="referrals_made",
    )
    referee_profile = models.OneToOneField(
        "accounts.ProfileBase",
        on_delete=models.CASCADE,
        related_name="referral_received",
    )

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
            models.CheckConstraint(
                check=~Q(referrer_profile=F("referee_profile")),
                name="chk_profile_referral_no_same_profile",
            ),
        ]
        indexes = [
            models.Index(fields=["referrer_user", "converted_at"]),
            models.Index(fields=["is_consumed"]),
        ]
    
    def clean(self):
        if self.referrer_profile_id and self.referrer_user_id:
            if self.referrer_profile.user_id != self.referrer_user_id:
                raise ValidationError("Referrer profile and referrer user mismatch.")
        if self.referee_profile_id and self.referee_user_id:
            if self.referee_profile.user_id != self.referee_user_id:
                raise ValidationError("Referee profile and referee user mismatch.")

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
