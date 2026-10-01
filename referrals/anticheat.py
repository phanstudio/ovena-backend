# referrals/anticheat.py
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.utils import timezone
from referrals.constants import (
    SUPPORTED_REFERRER_ROLES,
    SUPPORTED_REFEREE_ROLES,
    MAX_REFERRALS_PER_IP_24H,
    MIN_QUALIFYING_ORDER_AMOUNT_KOBO,
    FRAUD_STATUS_CLEAN,
    FRAUD_STATUS_FLAGGED,
    FRAUD_STATUS_REJECTED,
)
from referrals.models import ProfileReferral


def validate_referral_application(
    *,
    referrer_user,
    referee_user,
    referrer_role: str,
    referee_role: str,
    device_id: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, str]:
    """
    Validates a referral application for account eligibility and fraud vectors.
    Returns: (fraud_status, fraud_reason)
    Raises ValidationError if the application must be hard-blocked.
    """
    # 1. Account Validity
    if not referee_user or not getattr(referee_user, "is_active", False):
        raise ValidationError("Your account is not active.")

    if not referrer_user or not getattr(referrer_user, "is_active", False):
        raise ValidationError("The referring account is no longer active.")

    # 2. Role Restriction (Customers & Drivers supported; restaurants excluded for now)
    if referrer_role not in SUPPORTED_REFERRER_ROLES:
        raise ValidationError(
            f"The referral code belongs to an unsupported account type ({referrer_role})."
        )

    if referee_role not in SUPPORTED_REFEREE_ROLES:
        raise ValidationError(
            f"The referral program is currently only open to customers and drivers."
        )

    # 3. Self-Referral Prevention
    if referrer_user.id == referee_user.id:
        raise ValidationError("You cannot use your own referral code.")

    # 4. Circular Referral Prevention (A refers B, B refers A)
    is_circular = ProfileReferral.objects.filter(
        referrer_user=referee_user,
        referee_user=referrer_user,
    ).exists()
    if is_circular:
        raise ValidationError("Circular referral detected between these accounts.")

    # 5. IP Velocity Check (Rate limit bot farming)
    if ip_address:
        recent_ip_count = ProfileReferral.objects.filter(
            referee_ip_address=ip_address,
            created_at__gte=timezone.now() - timedelta(hours=24),
        ).count()
        if recent_ip_count >= MAX_REFERRALS_PER_IP_24H:
            raise ValidationError(
                "Too many referral signups from this network within 24 hours."
            )

    # 6. Device Fingerprint Collusion (Soft-flag for audit instead of hard-blocking innocent shared family phones)
    fraud_status = FRAUD_STATUS_CLEAN
    fraud_reason = ""

    if device_id:
        # Check if this device was previously used by the referrer
        device_matched_referrer = ProfileReferral.objects.filter(
            referee_device_id=device_id,
            referee_user=referrer_user,
        ).exists()

        if device_matched_referrer:
            fraud_status = FRAUD_STATUS_FLAGGED
            fraud_reason = "Referee device ID matches referrer device history."

    return fraud_status, fraud_reason


def validate_order_for_conversion(*, referral: ProfileReferral, order) -> tuple[bool, str]:
    """
    Evaluates whether a completed order qualifies for referral conversion.
    Returns: (is_valid, rejection_reason)
    """
    # 1. Ensure referral isn't already flagged/rejected
    if referral.fraud_status == FRAUD_STATUS_REJECTED:
        return False, "Referral marked as fraudulent."

    # 2. Minimum Basket Size Check (excluding discounts/coupons)
    sale = getattr(order, "sale", None)
    total_amount = getattr(sale, "amount", None) or getattr(order, "total_price", None) or 0
    if isinstance(total_amount, (int, float)) and total_amount < (MIN_QUALIFYING_ORDER_AMOUNT_KOBO / 100):
        return False, "Order subtotal is below the minimum qualifying referral threshold."

    # 3. Payment Method Collusion Check
    if sale and hasattr(sale, "paystack_auth_code") and sale.paystack_auth_code:
        from payments.models import Sale
        referrer_used_same_card = Sale.objects.filter(
            user=referral.referrer_user,
            paystack_auth_code=sale.paystack_auth_code,
        ).exists()
        if referrer_used_same_card:
            referral.fraud_status = FRAUD_STATUS_FLAGGED
            referral.fraud_reason = "Payment authorization code matches referrer's payment method."
            referral.save(update_fields=["fraud_status", "fraud_reason"])
            return False, "Payment method shared between referrer and referee."

    return True, ""
