from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
import hashlib
import json

from accounts.models import ProfileBase
from referrals.models import ProfileReferral, ReferralPayout
from django.db.models import Count, Q

REFERRALS_PER_UNIT = 10

def _normalized_code(code: str) -> str:
    return (code or "").strip().upper()


@transaction.atomic
def apply_referral_code(profile, code: str) -> ProfileReferral:
    code = _normalized_code(code)
    if not code:
        raise ValidationError("Referral code is required.")

    if ProfileReferral.objects.filter(referee_user=profile.user).exists():
        raise ValidationError("You already applied a referral code.")

    referrer_profile = (
        ProfileBase.objects.select_related("user")
        .filter(referral_code=code)
        .first()
    )
    referred_profile = (
        ProfileBase.objects.select_related("user")
        .filter(user=profile.user)
        .first()
    )
    if not referrer_profile:
        raise ValidationError("Invalid referral code.")

    if referrer_profile.user_id == referred_profile.user_id:
        raise ValidationError("You cannot use your own referral code.")

    return ProfileReferral.objects.create(
        referrer_profile=referrer_profile,
        referee_profile=referred_profile,
        referrer_user=referrer_profile.user,
        referee_user=referred_profile.user,
    )


def referral_count(profile) -> int:
    return ProfileReferral.objects.filter(referrer_user=profile.user).count()


def successful_referrals(profile) -> int:
    return ProfileReferral.objects.filter(
        referrer_user=profile.user,
        converted_at__isnull=False,
    ).count()


def referral_stats(profile):
    qs = ProfileReferral.objects.filter(referrer_user=profile.user)

    stats = qs.aggregate(
        total=Count("id"),
        successful=Count("id", filter=Q(converted_at__isnull=False)),
    )

    return {
        "total": stats["total"],
        "successful": stats["successful"],
        "pending": stats["total"] - stats["successful"],
    }


def referred_by(user):
    return ProfileReferral.objects.filter(
        referee_user=user,
    ).select_related("referrer_profile__user").first()


@transaction.atomic
def convert_referral_once(*, referee_profile) -> bool:
    try:
        referral = ProfileReferral.objects.select_for_update().get(referee_user=referee_profile.user)
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
