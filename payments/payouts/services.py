from __future__ import annotations

"""
payments/payouts/services.py

Core withdrawal service layer. The public API surface is unchanged:
  - get_balance_summary(user_id, role)
  - create_withdrawal_request(user_id, amount_kobo, idempotency_key, ...)
  - execute_realtime(withdrawal)
  - execute_batch(batch_date)
  - mark_withdrawal_paid(withdrawal)
  - mark_withdrawal_failed(withdrawal, reason)

What changed:
  - evaluate_eligibility() is now a thin import from eligibility.py
  - create_withdrawal_request resolves recipient_code via bridge.py
  - WithdrawalEligibilityEvaluator class removed from here (lives in eligibility.py)
"""

import logging
from datetime import date

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from payments.integrations.paystack.client import PaystackClient
from payments.models import User, Withdrawal
from payments.models import UserAccount
from payments.observability.metrics import increment
from payments.services.split_calculator import _create_ledger_entry, get_ledger_balance

# New: eligibility dispatcher and bridge
from payments.eligibility import WithdrawalDecision, evaluate_eligibility
from payments.payouts.bridge import resolve_recipient_code
from payments.payouts.constants import (
    MINIMUM_BY_ROLE
)
from payments.payouts.helper import (
    _coerce_strategy,
    _infer_ledger_role_for_user,
    _normalize_ledger_role,
    _pending_total
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
# Balance summary (unchanged)
# ---------------------------------------------------------------------------

def get_balance_summary(user_id, role: str | None = None):
    user = User.objects.get(id=user_id)
    balance = get_ledger_balance(user)
    pending = _pending_total(user)
    available = balance - pending

    if role:
        ledger_role = _normalize_ledger_role(role)
        minimum = MINIMUM_BY_ROLE.get(ledger_role or "", 0)
    else:
        try:
            minimum = MINIMUM_BY_ROLE.get(_infer_ledger_role_for_user(user), 0)
        except ValueError:
            minimum = 0

    return {
        "total_balance_kobo": balance,
        "pending_withdrawal_kobo": pending,
        "available_balance_kobo": available,
        "minimum_withdrawal_kobo": minimum,
        "can_withdraw": available >= minimum,
        "needed_to_withdraw_kobo": max(0, minimum - available),
        "total_balance_ngn": balance / 100,
        "available_balance_ngn": available / 100,
        "minimum_ngn": minimum / 100,
    }


# ---------------------------------------------------------------------------
# create_withdrawal_request — bridge wired in here
# ---------------------------------------------------------------------------

@transaction.atomic
def create_withdrawal_request(
    user_id: str,
    amount_kobo: int,
    idempotency_key: str,
    role: str | None = None,
    strategy: str | None = None,
    request_id: str | None = None,
):
    user = User.objects.select_for_update().get(id=user_id)
    strategy_value = _coerce_strategy(strategy)
    ledger_role = _normalize_ledger_role(role) or _infer_ledger_role_for_user(user)

    # Idempotency replay
    existing = (
        Withdrawal.objects.select_for_update()
        .filter(user=user, idempotency_key=idempotency_key)
        .first()
    )
    if existing:
        logger.info(
            "payments.withdrawal.request.replay",
            extra={
                "request_id": request_id or "",
                "idempotency_key": idempotency_key,
                "withdrawal_id": str(existing.id),
                "provider_ref": existing.paystack_transfer_ref or "",
            },
        )
        return existing, False

    # Eligibility — dispatches to the right evaluator via eligibility.py
    decision = evaluate_eligibility(user=user, amount_kobo=amount_kobo, role=ledger_role)
    if not decision.eligible:
        logger.warning(
            "payments.withdrawal.request.ineligible",
            extra={
                "request_id": request_id or "",
                "idempotency_key": idempotency_key,
                "withdrawal_id": "",
                "provider_ref": "",
                "checks": decision.checks,
            },
        )
        raise ValueError(f"Withdrawal eligibility failed: {decision.checks}")

    # Ledger hold
    hold_entry = _create_ledger_entry(
        user=user,
        sale=None,
        role=ledger_role,
        entry_type="debit",
        amount=-amount_kobo,
        notes="Hold for withdrawal request",
    )

    # Bridge resolves recipient_code from the correct account model
    # (BusinessPayoutAccount for business_owner, UserAccount for everyone else)
    recipient_code = resolve_recipient_code(user, ledger_role)

    withdrawal = Withdrawal.objects.create(
        user=user,
        amount=amount_kobo,
        status="pending_batch",
        strategy=strategy_value,
        idempotency_key=idempotency_key,
        paystack_recipient_code=recipient_code,
        ledger_entry=hold_entry,
    )

    logger.info(
        "payments.withdrawal.request.created",
        extra={
            "request_id": request_id or "",
            "idempotency_key": idempotency_key,
            "withdrawal_id": str(withdrawal.id),
            "provider_ref": "",
        },
    )
    return withdrawal, True


# ---------------------------------------------------------------------------
# Execution pipeline — unchanged
# ---------------------------------------------------------------------------

@transaction.atomic
def process_withdrawal_request(withdrawal: Withdrawal):
    """Legacy alias kept for compatibility."""
    if withdrawal.strategy == STRATEGY_REALTIME:
        return execute_realtime(withdrawal)
    return withdrawal


@transaction.atomic
def execute_realtime(withdrawal: Withdrawal):
    if withdrawal.status not in {"pending_batch", "processing"}:
        return withdrawal

    logger.info(
        "payments.withdrawal.realtime.start",
        extra={
            "request_id": "",
            "idempotency_key": withdrawal.idempotency_key or "",
            "withdrawal_id": str(withdrawal.id),
            "provider_ref": withdrawal.paystack_transfer_ref or "",
        },
    )

    withdrawal.status = "processing"
    withdrawal.processed_at = timezone.now()
    withdrawal.save(update_fields=["status", "processed_at"])

    payload = {
        "source": "balance",
        "amount": int(withdrawal.amount),
        "recipient": withdrawal.paystack_recipient_code,
        "reason": f"Withdrawal {withdrawal.id}",
    }
    result = paystack_client.initiate_transfer(payload).get("data", {})

    withdrawal.paystack_transfer_ref = result.get("reference") or withdrawal.paystack_transfer_ref
    withdrawal.paystack_transfer_code = result.get("transfer_code", "")
    withdrawal.save(update_fields=["paystack_transfer_ref", "paystack_transfer_code"])

    logger.info(
        "payments.withdrawal.realtime.accepted",
        extra={
            "request_id": "",
            "idempotency_key": withdrawal.idempotency_key or "",
            "withdrawal_id": str(withdrawal.id),
            "provider_ref": withdrawal.paystack_transfer_ref or withdrawal.paystack_transfer_code or "",
        },
    )
    return withdrawal


@transaction.atomic
def execute_batch(batch_date: date | None = None) -> dict:
    run_date = batch_date or date.today()
    pending = list(
        Withdrawal.objects.select_for_update()
        .filter(status="pending_batch", strategy=STRATEGY_BATCH)
        .order_by("requested_at")
    )
    if not pending:
        return {"batch_date": str(run_date), "count": 0, "queued": 0}

    logger.info(
        "payments.withdrawal.batch.start",
        extra={
            "request_id": "",
            "idempotency_key": "",
            "withdrawal_id": "",
            "provider_ref": "",
            "count": len(pending),
            "batch_date": run_date.isoformat(),
        },
    )

    for withdrawal in pending:
        withdrawal.status = "processing"
        withdrawal.batch_date = run_date
        withdrawal.processed_at = timezone.now()
        withdrawal.save(update_fields=["status", "batch_date", "processed_at"])

    transfers = [
        {
            "amount": int(w.amount),
            "recipient": w.paystack_recipient_code,
            "reference": f"BATCH_{str(w.id).replace('-', '')[:20]}",
            "reason": f"Batch payout {run_date.isoformat()}",
        }
        for w in pending
    ]

    result = paystack_client.bulk_transfer({"currency": "NGN", "transfers": transfers})
    payloads = result.get("data", [])

    for idx, withdrawal in enumerate(pending):
        row = payloads[idx] if idx < len(payloads) else {}
        withdrawal.paystack_transfer_ref = row.get("reference") or transfers[idx]["reference"]
        withdrawal.paystack_transfer_code = row.get("transfer_code", "")
        withdrawal.save(update_fields=["paystack_transfer_ref", "paystack_transfer_code"])

    return {"batch_date": str(run_date), "count": len(pending), "queued": len(pending)}


@transaction.atomic
def mark_withdrawal_paid(withdrawal: Withdrawal):
    if withdrawal.status == "complete":
        return withdrawal
    withdrawal.status = "complete"
    withdrawal.completed_at = timezone.now()
    withdrawal.save(update_fields=["status", "completed_at"])

    increment("payments.payout.success_total", tags={"strategy": withdrawal.strategy})
    logger.info(
        "payments.withdrawal.complete",
        extra={
            "request_id": "",
            "idempotency_key": withdrawal.idempotency_key or "",
            "withdrawal_id": str(withdrawal.id),
            "provider_ref": withdrawal.paystack_transfer_ref or withdrawal.paystack_transfer_code or "",
        },
    )
    return withdrawal


@transaction.atomic
def mark_withdrawal_failed(withdrawal: Withdrawal, reason: str):
    withdrawal.status = "failed"
    withdrawal.failure_reason = reason
    withdrawal.save(update_fields=["status", "failure_reason"])

    role = None
    if withdrawal.ledger_entry_id:
        try:
            role = _normalize_ledger_role(withdrawal.ledger_entry.role)
        except Exception:
            role = None
    ledger_role = role or _infer_ledger_role_for_user(withdrawal.user)

    _create_ledger_entry(
        user=withdrawal.user,
        sale=None,
        role=ledger_role,
        entry_type="credit",
        amount=withdrawal.amount,
        notes=f"Release hold for failed withdrawal {withdrawal.id}",
    )

    increment("payments.payout.failed_total", tags={"strategy": withdrawal.strategy})
    logger.warning(
        "payments.withdrawal.failed",
        extra={
            "request_id": "",
            "idempotency_key": withdrawal.idempotency_key or "",
            "withdrawal_id": str(withdrawal.id),
            "provider_ref": withdrawal.paystack_transfer_ref or withdrawal.paystack_transfer_code or "",
            "reason": reason,
        },
    )
    return withdrawal
