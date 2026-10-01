from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
import hashlib
import json

from accounts.models import CustomerProfile, DriverProfile
from referrals.models import ProfileReferral, ReferralPayout
from referrals.constants import (
    ROLE_CUSTOMER,
    ROLE_DRIVER,
    FRAUD_STATUS_CLEAN,
    REFERRALS_PER_UNIT,
)
from referrals.anticheat import (
    validate_referral_application,
    validate_order_for_conversion,
)
from django.db.models import Count, Q


def _normalized_code(code: str) -> str:
    return (code or "").strip().upper()


@transaction.atomic
def apply_referral_code(
    *,
    code: str,
    user=None,
    profile=None,
    role: str = ROLE_CUSTOMER,
    device_id: str | None = None,
    ip_address: str | None = None,
) -> ProfileReferral:
    """
    Applies a referral code for a referee user.
    Accepts either `user` (preferred) or legacy `profile`.
    Ensures active accounts and anti-cheat validation.
    """
    code = _normalized_code(code)
    if not code:
        raise ValidationError("Referral code is required.")

    # Resolve referee user
    if profile is not None:
        referee_user = profile.user
        role = getattr(profile, "profile_type", role)
    elif user is not None:
        referee_user = user
    else:
        raise ValidationError("User or profile is required to apply a referral code.")

    if ProfileReferral.objects.filter(referee_user=referee_user).exists():
        raise ValidationError("You have already applied a referral code.")

    # Find referrer user and role across supported standalone profile models
    referrer_customer = CustomerProfile.objects.select_related("user").filter(referral_code=code).first()
    if referrer_customer:
        referrer_user = referrer_customer.user
        referrer_role = ROLE_CUSTOMER
    else:
        referrer_driver = DriverProfile.objects.select_related("user").filter(referral_code=code).first()
        if referrer_driver:
            referrer_user = referrer_driver.user
            referrer_role = ROLE_DRIVER
        else:
            raise ValidationError("Invalid referral code.")

    # Anti-Cheat & Role Validation
    fraud_status, fraud_reason = validate_referral_application(
        referrer_user=referrer_user,
        referee_user=referee_user,
        referrer_role=referrer_role,
        referee_role=role,
        device_id=device_id,
        ip_address=ip_address,
    )

    return ProfileReferral.objects.create(
        referrer_user=referrer_user,
        referee_user=referee_user,
        referrer_role=referrer_role,
        referee_role=role,
        referee_device_id=device_id,
        referee_ip_address=ip_address,
        fraud_status=fraud_status,
        fraud_reason=fraud_reason,
    )


def referral_count(user_or_profile) -> int:
    user = getattr(user_or_profile, "user", user_or_profile)
    return ProfileReferral.objects.filter(referrer_user=user).count()


def successful_referrals(user_or_profile) -> int:
    user = getattr(user_or_profile, "user", user_or_profile)
    return ProfileReferral.objects.filter(
        referrer_user=user,
        converted_at__isnull=False,
    ).count()


def referral_stats(user_or_profile):
    user = getattr(user_or_profile, "user", user_or_profile)
    qs = ProfileReferral.objects.filter(referrer_user=user)

    stats = qs.aggregate(
        total=Count("id"),
        successful=Count("id", filter=Q(converted_at__isnull=False)),
    )

    return {
        "total": stats["total"],
        "successful": stats["successful"],
        "pending": stats["total"] - stats["successful"],
    }


def referred_by(user_or_profile):
    user = getattr(user_or_profile, "user", user_or_profile)
    return ProfileReferral.objects.filter(
        referee_user=user,
    ).select_related("referrer_user").first()


# 🎯 CONVERSION ENGINES

@transaction.atomic
def convert_referral_for_customer(*, user, order) -> bool:
    """
    Converts a customer referral upon their qualifying delivered order.
    Evaluates anti-cheat fraud criteria (min basket size, card collision).
    """
    try:
        referral = ProfileReferral.objects.select_for_update().get(
            referee_user=user,
            referee_role=ROLE_CUSTOMER,
        )
    except ProfileReferral.DoesNotExist:
        return False

    if referral.converted_at is not None:
        return False

    # Anti-cheat evaluation
    is_valid, reason = validate_order_for_conversion(referral=referral, order=order)
    if not is_valid:
        return False

    referral.converted_at = timezone.now()
    referral.save(update_fields=["converted_at", "fraud_status", "fraud_reason"])
    return True


@transaction.atomic
def convert_referral_for_driver(*, user, driver_profile=None) -> bool:
    """
    Converts a driver referral upon their first completed delivery.
    """
    try:
        referral = ProfileReferral.objects.select_for_update().get(
            referee_user=user,
            referee_role=ROLE_DRIVER,
        )
    except ProfileReferral.DoesNotExist:
        return False

    if referral.converted_at is not None:
        return False

    referral.converted_at = timezone.now()
    referral.save(update_fields=["converted_at"])
    return True


@transaction.atomic
def convert_referral_once(*, referee_profile=None, referee_user=None, order=None) -> bool:
    """
    Backward-compatible conversion dispatcher.
    """
    user = referee_user
    if user is None and referee_profile is not None:
        user = getattr(referee_profile, "user", None)

    if not user:
        return False

    profile_type = getattr(referee_profile, "profile_type", None)
    if profile_type == ROLE_DRIVER:
        return convert_referral_for_driver(user=user, driver_profile=referee_profile)

    return convert_referral_for_customer(user=user, order=order)


## Admin section
# 🔐 HASHING

def generate_snapshot_hash(snapshot: list) -> str:
    payload = json.dumps(snapshot, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def verify_snapshot_integrity(payout: ReferralPayout) -> bool:
    expected = generate_snapshot_hash(payout.referral_snapshot)
    return expected == payout.snapshot_hash


# 💰 PAYOUT

@transaction.atomic
def process_referral_payout(*, user, units=None, mode="partial"):
    """
    Processes referral payouts for clean, converted, unconsumed referrals.
    """
    qs = (
        ProfileReferral.objects
        .select_for_update()
        .select_related("referee_user")
        .filter(
            referrer_user=user,
            converted_at__isnull=False,
            is_consumed=False,
            fraud_status=FRAUD_STATUS_CLEAN,  # Anti-cheat: Only unflagged referrals are paid
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
            raise ValueError("Not enough clean referrals available for payout")

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
