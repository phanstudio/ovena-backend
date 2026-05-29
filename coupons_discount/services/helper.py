from django.db.models import F, Q
from django.utils import timezone
from datetime import timedelta


# ---------------------------------------------------------------------------
# Reusable Q-object helpers
# ---------------------------------------------------------------------------

def eligible_coupon_q() -> Q:
    """
    A coupon is eligible (regardless of type) when:
      - is_active
      - valid window is open
      - uses not exhausted (max_uses is null OR uses_count < max_uses)

    Used for marketing coupons at redemption time.
    """
    now = timezone.now()
    return (
        Q(is_active=True)
        & Q(valid_from__lte=now)
        & (Q(valid_until__isnull=True) | Q(valid_until__gte=now))
        & (Q(max_uses__isnull=True) | Q(uses_count__lt=F("max_uses")))
    )


def eligible_coupon_for_wheel_q() -> Q:
    """
    Same validity window as eligible_coupon_q PLUS must be a reward coupon.
    Used when populating / spinning the wheel.
    """
    return eligible_coupon_q() & Q(is_reward=True)


def eligible_coupon_for_wheel_with_min_lifetime_q(
    hours: int = 6,
) -> Q:
    """
    Reward coupons that will remain valid for at least `hours`
    from the current time.
    """
    minimum_expiry = timezone.now() + timedelta(hours=hours)

    return (
        eligible_coupon_for_wheel_q()
        & (
            Q(valid_until__isnull=True)
            | Q(valid_until__gte=minimum_expiry)
        )
    )


def available_wallet_entry_q() -> Q:
    """
    A wallet entry is available for redemption when not yet used.
    The underlying coupon's validity is checked separately via eligible_coupon_q
    on the coupon itself — wallet entries don't expire independently.
    """
    return Q(is_used=False)
