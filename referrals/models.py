from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q


class ProfileReferral(models.Model):
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

    created_at = models.DateTimeField(auto_now_add=True)
    converted_at = models.DateTimeField(null=True, blank=True)

    reward_issued = models.BooleanField(default=False)
    reward_issued_at = models.DateTimeField(null=True, blank=True)

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
            models.Index(fields=["referrer_profile", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def clean(self):
        if self.referrer_profile_id and self.referrer_user_id:
            if self.referrer_profile.user_id != self.referrer_user_id:
                raise ValidationError("Referrer profile and referrer user mismatch.")
        if self.referee_profile_id and self.referee_user_id:
            if self.referee_profile.user_id != self.referee_user_id:
                raise ValidationError("Referee profile and referee user mismatch.")

