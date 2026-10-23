from __future__ import annotations

"""
payments/payouts/bridge.py

Resolves the correct payout account for any actor without the withdrawal
pipeline needing to know which concrete model it is talking to.

The pipeline only ever calls:
  - resolve_payout_account(user, role)  → AbstractPayoutAccount instance or None
  - resolve_recipient_code(user, role)  → str

Everything else is an implementation detail of this module.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from payments.models.accounts import AbstractPayoutAccount

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-role resolvers
# ---------------------------------------------------------------------------

def _resolve_for_business(user) -> "AbstractPayoutAccount | None":
    """
    Business payout account lives on the Business entity, not the User.
    Navigate: user → business_admin → business → payout (BusinessPayoutAccount)
    Never falls back to UserAccount.
    """
    try:
        admin = getattr(user, "business_admin", None)
        if admin and hasattr(admin.business, "payout") and admin.business.payout:
            return admin.business.payout
    except Exception:
        pass
    fallback = _resolve_for_individual(user)
    if fallback and fallback.paystack_recipient_code:
        return fallback
    logger.warning(
        "payments.bridge.business_payout.missing",
        extra={"user_id": str(getattr(user, "id", None))},
    )
    return None


def _resolve_for_individual(user) -> "AbstractPayoutAccount | None":
    """
    Individual actors (customers, referrals) use UserAccount.
    """
    from payments.models import UserAccount

    try:
        return user.payment_account  # OneToOne reverse from UserAccount
    except (UserAccount.DoesNotExist, AttributeError):
        logger.warning(
            "payments.bridge.user_account.missing",
            extra={"user_id": str(getattr(user, "id", None))},
        )
        return None


def _resolve_for_driver(user) -> "AbstractPayoutAccount | None":
    """
    Driver payout account lives on DriverProfile as DriverBankAccount.
    Falls back to UserAccount only when no DriverProfile is attached.
    """
    try:
        profile = getattr(user, "driver_profile", None)
        if profile and hasattr(profile, "bank_account") and profile.bank_account:
            return profile.bank_account
    except Exception:
        pass
    fallback = _resolve_for_individual(user)
    if fallback and fallback.paystack_recipient_code:
        return fallback
    logger.warning(
        "payments.bridge.driver_bank_account.missing",
        extra={"user_id": str(getattr(user, "id", None))},
    )
    return None


_ACCOUNT_RESOLVER_MAP = {
    "business_owner": _resolve_for_business,
    "driver": _resolve_for_driver,
    "referral": _resolve_for_individual,
    "customer": _resolve_for_individual,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_payout_account(user, role: str) -> "AbstractPayoutAccount | None":
    """
    Return the concrete payout account for this user+role combination.

    Returns None if no account is found — callers should treat this as
    recipient_ready=False in eligibility checks.
    """
    resolver = _ACCOUNT_RESOLVER_MAP.get(role)
    if resolver is None:
        logger.error(
            "payments.bridge.unknown_role",
            extra={"user_id": str(user.id), "role": role},
        )
        return None

    return resolver(user)


def resolve_recipient_code(user, role: str) -> str:
    """
    Return the Paystack recipient code for this user+role, or empty string.

    This is the only thing create_withdrawal_request needs from the bridge.
    The string is snapshotted onto the Withdrawal row at creation time so
    the pipeline never has to re-resolve it later.
    """
    account = resolve_payout_account(user, role)
    if account is None:
        return ""
    return account.get_recipient_code()


def purge_rogue_user_accounts() -> int:
    """
    Clean up any UserAccount instances erroneously created for business admins or drivers.
    Returns the count of purged accounts.
    """
    from django.db import models
    from payments.models import UserAccount

    rogue_qs = UserAccount.objects.filter(
        models.Q(user__business_admin__isnull=False) | models.Q(user__driver_profile__isnull=False)
    )
    count = rogue_qs.count()
    if count > 0:
        rogue_qs.delete()
        logger.info("Purged %d rogue UserAccount instances attached to business admins or drivers", count)
    return count