from django.db.models import F, Q
from django.utils import timezone

def eligible_coupon_q():
    """
    Coupon is eligible if:
    - is_active
    - valid window ok
    - AND (max_uses is null OR uses_count < max_uses)
    """
    now = timezone.now()
    return (
        Q(is_active=True)
        & Q(valid_from__lte=now)
        & (Q(valid_until__isnull=True) | Q(valid_until__gte=now))
        & (Q(max_uses__isnull=True) | Q(uses_count__lt=F("max_uses")))
    )
