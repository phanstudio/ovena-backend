
from __future__ import annotations
import logging
from django.db.models import Sum

from payments.integrations.paystack.client import PaystackClient
from payments.models import User, Withdrawal
from payments.payouts.constants import (
    MINIMUM_BY_ROLE
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


STRATEGY_BATCH = Withdrawal.STRATEGY_BATCH
STRATEGY_REALTIME = Withdrawal.STRATEGY_REALTIME

LEDGER_WITHDRAWAL_ROLES = frozenset(MINIMUM_BY_ROLE.keys())

paystack_client = PaystackClient()


# ---------------------------------------------------------------------------
# Helpers (still used by eligibility.py via import)
# ---------------------------------------------------------------------------

def _normalize_ledger_role(role: str | None) -> str | None:
    if role is None:
        return None
    value = str(role).lower().strip()
    if not value:
        return None
    if value not in LEDGER_WITHDRAWAL_ROLES:
        raise ValueError(
            f"Invalid ledger role '{role}'. Expected one of: {sorted(LEDGER_WITHDRAWAL_ROLES)}"
        )
    return value


def _infer_ledger_role_for_user(user: User) -> str:
    try:
        from payments.models import LedgerEntry
    except Exception:
        LedgerEntry = None  # type: ignore

    if LedgerEntry is not None:
        last_role = (
            LedgerEntry.objects.filter(user=user)
            .order_by("-created_at")
            .values_list("role", flat=True)
            .first()
        )
        try:
            normalized = _normalize_ledger_role(last_role)
        except ValueError:
            normalized = None
        if normalized:
            return normalized

    if getattr(user, "driver_profile", None):
        return "driver"
    if getattr(user, "business_admin", None):
        return "business_owner"

    raise ValueError(
        "Unable to infer ledger role for withdrawals. "
        "Provide an explicit 'role' (driver|business_owner|referral) or "
        "ensure the user has ledger entries."
    )


def _pending_total(user) -> int:
    result = Withdrawal.objects.filter(
        user=user, status="pending_batch"
    ).aggregate(total=Sum("amount"))
    return result["total"] or 0


def _coerce_strategy(strategy: str | None) -> str:
    value = (strategy or STRATEGY_BATCH).lower().strip()
    if value not in {STRATEGY_BATCH, STRATEGY_REALTIME}:
        raise ValueError("Invalid payout strategy. Use 'batch' or 'realtime'.")
    return value
