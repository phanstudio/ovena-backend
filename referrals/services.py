from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import CustomerProfile, DriverProfile, ProfileBase
from referrals.models import ProfileReferral


def _normalized_code(code: str) -> str:
    return (code or "").strip().upper()


def _ensure_profile_base(profile) -> ProfileBase:
    if isinstance(profile, ProfileBase):
        return profile

    if isinstance(profile, CustomerProfile):
        if profile.base_profile_id:
            return profile.base_profile
        base = ProfileBase.objects.create(
            user=profile.user,
            profile_type=ProfileBase.PROFILE_CUSTOMER,
        )
        profile.base_profile = base
        profile.save(update_fields=["base_profile"])
        return base

    if isinstance(profile, DriverProfile):
        if profile.base_profile_id:
            return profile.base_profile
        base = ProfileBase.objects.create(
            user=profile.user,
            profile_type=ProfileBase.PROFILE_DRIVER,
        )
        profile.base_profile = base
        profile.save(update_fields=["base_profile"])
        return base

    raise ValidationError("Unsupported profile type.")


def ensure_profile_base(profile) -> ProfileBase:
    return _ensure_profile_base(profile)


@transaction.atomic
def apply_referral_code(profile, code: str) -> ProfileReferral:
    code = _normalized_code(code)
    if not code:
        raise ValidationError("Referral code is required.")

    referee_profile = _ensure_profile_base(profile)

    if ProfileReferral.objects.filter(referee_user=referee_profile.user).exists():
        raise ValidationError("You already applied a referral code.")

    referrer_profile = (
        ProfileBase.objects.select_related("user")
        .filter(referral_code=code)
        .first()
    )
    if not referrer_profile:
        raise ValidationError("Invalid referral code.")

    if referrer_profile.user_id == referee_profile.user_id:
        raise ValidationError("You cannot use your own referral code.")

    return ProfileReferral.objects.create(
        referrer_profile=referrer_profile,
        referee_profile=referee_profile,
        referrer_user=referrer_profile.user,
        referee_user=referee_profile.user,
    )


def referral_count(profile) -> int:
    base = _ensure_profile_base(profile)
    return ProfileReferral.objects.filter(referrer_user=base.user).count()


def successful_referrals(profile) -> int:
    base = _ensure_profile_base(profile)
    return ProfileReferral.objects.filter(
        referrer_user=base.user,
        converted_at__isnull=False,
    ).count()


def referred_by(user):
    return ProfileReferral.objects.filter(
        referee_user=user,
    ).first()

@transaction.atomic
def convert_referral_once(*, referee_profile) -> bool:
    base = _ensure_profile_base(referee_profile)
    try:
        referral = ProfileReferral.objects.select_for_update().get(referee_user=base.user)
    except ProfileReferral.DoesNotExist:
        return False

    if referral.converted_at is not None:
        return False

    referral.converted_at = timezone.now()
    referral.save(update_fields=["converted_at"])
    return True
