from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
import hashlib
import json

from accounts.models import CustomerProfile, DriverProfile, ProfileBase
from referrals.models import ProfileReferral, ReferralPayout

REFERRALS_PER_UNIT = 10

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

## Admin section
# 🔐 HASHING

def generate_snapshot_hash(snapshot: list) -> str:
    payload = json.dumps(snapshot, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()

def verify_snapshot_integrity(payout: ReferralPayout) -> bool:
    expected = generate_snapshot_hash(payout.referral_snapshot)
    return expected == payout.snapshot_hash


# 🎯 CONVERSION

def convert_referred_user_once(*, referee_user):
    try:
        referral = ProfileReferral.objects.select_for_update().get(
            referee_user=referee_user
        )
    except ProfileReferral.DoesNotExist:
        return False

    if referral.converted_at:
        return False

    referral.converted_at = timezone.now()
    referral.save(update_fields=["converted_at"])
    return True


# 💰 PAYOUT

@transaction.atomic
def process_referral_payout(*, user, units=None, mode="partial"):
    qs = (
        ProfileReferral.objects
        .select_for_update()
        .select_related("referee_user")
        .filter(
            referrer_user=user,
            converted_at__isnull=False,
            is_consumed=False
        )
        .order_by("converted_at", "id")
    )

    total_available = qs.count()

    if mode == "all":
        units_paid = total_available // REFERRALS_PER_UNIT
        use_count = units_paid * REFERRALS_PER_UNIT
    else:
        if not units:
            raise ValueError("Units required for partial payout")

        use_count = units * REFERRALS_PER_UNIT
        if total_available < use_count:
            raise ValueError("Not enough referrals")

        units_paid = units

    referrals = list(qs[:use_count])

    # 🔥 SNAPSHOT BEFORE UPDATE
    snapshot = [
        {
            "referral_id": str(r.id),
            "referee_user_id": r.referee_user_id,
            "converted_at": r.converted_at.isoformat(),
        }
        for r in referrals
    ]

    snapshot_hash = generate_snapshot_hash(snapshot)

    # mark consumed
    ProfileReferral.objects.filter(
        id__in=[r.id for r in referrals]
    ).update(
        is_consumed=True,
        consumed_at=timezone.now()
    )

    payout = ReferralPayout.objects.create(
        user=user,
        units_paid=units_paid,
        referral_snapshot=snapshot,
        snapshot_hash=snapshot_hash,
        conversion_rate=REFERRALS_PER_UNIT,
    )

    return payout
