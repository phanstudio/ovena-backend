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
from payments.integrations.paystack.errors import PaystackAPIError, PaystackRequestError
from payments.models import User, Withdrawal
from payments.models import UserAccount
from payments.observability.metrics import increment
from payments.services.split_calculator import _create_ledger_entry, get_ledger_balance
from payments.services.ledger_audit import (
    verify_user_ledger_chain_since_last_withdrawal,
    flag_withdrawal,
)
from accounts.services.security_guards import (
    is_security_cooldown_active,
    is_pin_locked,
)

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
    # Withdrawal requests create a ledger debit hold immediately, so the ledger
    # balance is already the available balance. Add pending back for total.
    debt = max(0, -balance)
    available = max(0, balance)
    total = balance + pending

    if role:
        ledger_role = _normalize_ledger_role(role)
        minimum = MINIMUM_BY_ROLE.get(ledger_role or "", 0)
    else:
        try:
            minimum = MINIMUM_BY_ROLE.get(_infer_ledger_role_for_user(user), 0)
        except ValueError:
            minimum = 0

    return {
        "total_balance_kobo": total,
        "pending_withdrawal_kobo": pending,
        "available_balance_kobo": available,
        "outstanding_debt_kobo": debt,
        "minimum_withdrawal_kobo": minimum,
        "can_withdraw": available >= minimum and balance > 0,
        "needed_to_withdraw_kobo": max(0, minimum - available),
        "total_balance_ngn": total / 100,
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
    if not isinstance(amount_kobo, int) or amount_kobo <= 0:
        raise ValueError("amount_kobo must be a positive integer greater than 0")

    user = User.objects.select_for_update().get(id=user_id)
    strategy_value = _coerce_strategy(strategy)
    ledger_role = _normalize_ledger_role(role) or _infer_ledger_role_for_user(user)

    # Server-side security cooldown and PIN lock enforcement
    cooldown_active, rem_sec = is_security_cooldown_active(user)
    if cooldown_active:
        raise ValueError(
            f"Withdrawals are temporarily paused due to recent security updates on your account. Try again in {max(1, rem_sec // 3600)} hour(s)."
        )

    pin_locked, rem_lock = is_pin_locked(user.id)
    if pin_locked:
        raise ValueError(
            f"Transaction PIN is locked due to multiple failed attempts. Try again in {max(1, rem_lock // 60)} minute(s)."
        )

    # Idempotency replay: verify amount matches
    existing = (
        Withdrawal.objects.select_for_update()
        .filter(user=user, idempotency_key=idempotency_key)
        .first()
    )
    if existing:
        if existing.amount != amount_kobo:
            raise ValueError(
                f"Idempotency key reused with different amount: {amount_kobo} != {existing.amount}"
            )
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

    # Validate recipient code BEFORE creating ledger hold
    recipient_code = resolve_recipient_code(user, ledger_role)
    if not recipient_code:
        raise ValueError(f"No payout recipient code configured for user {user.id} ({ledger_role})")

    # Ledger hold
    hold_entry = _create_ledger_entry(
        user=user,
        sale=None,
        role=ledger_role,
        entry_type="debit",
        amount=-amount_kobo,
        notes="Hold for withdrawal request",
    )

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

def _claim_for_payout(withdrawal_id) -> Withdrawal | None:
    with transaction.atomic():
        w = Withdrawal.objects.select_for_update().filter(id=withdrawal_id).first()
        if not w or w.status != "pending_batch" or w.is_flagged:
            return None
        w.status = "processing"
        w.processed_at = timezone.now()
        w.paystack_transfer_ref = w.paystack_transfer_ref or f"wd_{w.id.hex}"
        w.save(update_fields=["status", "processed_at", "paystack_transfer_ref"])
        return w


def execute_realtime(withdrawal: Withdrawal):
    w = _claim_for_payout(withdrawal.id)
    if w is None:
        return Withdrawal.objects.filter(id=withdrawal.id).first() or withdrawal

    # Ledger tamper audit before dispatching funds
    is_valid, reason, failed_ids = verify_user_ledger_chain_since_last_withdrawal(w.user)
    if not is_valid:
        logger.critical(
            "payments.withdrawal.realtime.tampering_detected",
            extra={"withdrawal_id": str(w.id), "user_id": str(w.user_id), "reason": reason},
        )
        flag_withdrawal(w, reason=reason, failed_entry_ids=failed_ids)
        return w

    logger.info(
        "payments.withdrawal.realtime.start",
        extra={
            "idempotency_key": w.idempotency_key or "",
            "withdrawal_id": str(w.id),
            "provider_ref": w.paystack_transfer_ref,
        },
    )

    payload = {
        "source": "balance",
        "amount": int(w.amount),
        "recipient": w.paystack_recipient_code,
        "reference": w.paystack_transfer_ref,
        "reason": f"Withdrawal {w.id}",
    }

    try:
        result = paystack_client.initiate_transfer(payload).get("data", {})
        w.paystack_transfer_code = result.get("transfer_code", "")
        w.save(update_fields=["paystack_transfer_code"])
        logger.info(
            "payments.withdrawal.realtime.accepted",
            extra={
                "idempotency_key": w.idempotency_key or "",
                "withdrawal_id": str(w.id),
                "provider_ref": w.paystack_transfer_ref,
                "transfer_code": w.paystack_transfer_code,
            },
        )
        return w
    except PaystackAPIError as exc:
        # Definite rejection (4xx, rejected account/recipient): fail and refund
        logger.warning(
            "payments.withdrawal.realtime.rejected",
            extra={"withdrawal_id": str(w.id), "error": str(exc)},
        )
        mark_withdrawal_failed(w, str(exc))
        return Withdrawal.objects.get(id=w.id)
    except Exception as exc:
        # Network timeout / 5xx: unknown outcome, leave processing for reconcile to verify by reference
        logger.exception(
            "payments.withdrawal.realtime.outcome_unknown",
            extra={"withdrawal_id": str(w.id), "error": str(exc)},
        )
        return Withdrawal.objects.get(id=w.id)


def execute_batch(batch_date: date | None = None) -> dict:
    run_date = batch_date or timezone.localdate()

    with transaction.atomic():
        pending = list(
            Withdrawal.objects.select_for_update(skip_locked=True)
            .filter(status="pending_batch", strategy=STRATEGY_BATCH, is_flagged=False)
            .order_by("requested_at")
        )
        if not pending:
            return {"batch_date": str(run_date), "count": 0, "queued": 0}

        valid_pending = []
        for withdrawal in pending:
            is_valid, reason, failed_ids = verify_user_ledger_chain_since_last_withdrawal(withdrawal.user)
            if not is_valid:
                logger.critical(
                    "payments.withdrawal.batch.tampering_detected",
                    extra={
                        "withdrawal_id": str(withdrawal.id),
                        "user_id": str(withdrawal.user_id),
                        "reason": reason,
                    },
                )
                flag_withdrawal(withdrawal, reason=reason, failed_entry_ids=failed_ids)
                continue

            withdrawal.status = "processing"
            withdrawal.batch_date = run_date
            withdrawal.processed_at = timezone.now()
            withdrawal.paystack_transfer_ref = withdrawal.paystack_transfer_ref or f"wd_{withdrawal.id.hex}"
            withdrawal.save(update_fields=["status", "batch_date", "processed_at", "paystack_transfer_ref"])
            valid_pending.append(withdrawal)

    if not valid_pending:
        logger.warning("payments.withdrawal.batch.no_valid_transfers", extra={"batch_date": run_date.isoformat()})
        return {"batch_date": str(run_date), "count": 0, "queued": 0}

    transfers = [
        {
            "amount": int(w.amount),
            "recipient": w.paystack_recipient_code,
            "reference": w.paystack_transfer_ref,
            "reason": f"Batch payout {run_date.isoformat()}",
        }
        for w in valid_pending
    ]

    try:
        result = paystack_client.bulk_transfer({"currency": "NGN", "transfers": transfers})
        payloads = result.get("data", [])
    except Exception as exc:
        logger.exception("payments.withdrawal.batch.transfer_failed", extra={"count": len(valid_pending)})
        return {"batch_date": str(run_date), "count": len(valid_pending), "queued": 0, "error": str(exc)}

    response_map = {
        row.get("reference"): row
        for row in payloads
        if isinstance(row, dict) and row.get("reference")
    }

    for w in valid_pending:
        row = response_map.get(w.paystack_transfer_ref)
        if row:
            w.paystack_transfer_code = row.get("transfer_code", "")
            w.save(update_fields=["paystack_transfer_code"])
            status_str = (row.get("status") or "").lower().strip()
            if status_str in ("failed", "rejected"):
                mark_withdrawal_failed(w, row.get("reason") or "Paystack bulk transfer item rejected")

    return {"batch_date": str(run_date), "count": len(valid_pending), "queued": len(valid_pending)}


@transaction.atomic
def mark_withdrawal_paid(withdrawal: Withdrawal):
    w = Withdrawal.objects.select_for_update().get(pk=withdrawal.pk)
    if w.status == "complete":
        return w
    if w.status in ("failed", "reversed"):
        logger.critical(
            "payments.withdrawal.paid_after_failed_or_reversed",
            extra={"withdrawal_id": str(w.id), "status": w.status},
        )
        return w
    if w.status not in ("pending_batch", "processing"):
        return w

    w.status = "complete"
    w.completed_at = timezone.now()
    w.save(update_fields=["status", "completed_at"])

    transaction.on_commit(lambda: increment("payments.payout.success_total", tags={"strategy": w.strategy}))
    logger.info(
        "payments.withdrawal.complete",
        extra={
            "request_id": "",
            "idempotency_key": w.idempotency_key or "",
            "withdrawal_id": str(w.id),
            "provider_ref": w.paystack_transfer_ref or w.paystack_transfer_code or "",
        },
    )
    return w


@transaction.atomic
def mark_withdrawal_failed(withdrawal: Withdrawal, reason: str):
    w = Withdrawal.objects.select_for_update().select_related("user", "ledger_entry").get(pk=withdrawal.pk)
    if w.status == "failed":
        return w
    if w.status == "complete":
        logger.critical("payments.withdrawal.fail_after_complete", extra={"withdrawal_id": str(w.id)})
        return w
    if w.status not in ("pending_batch", "processing"):
        return w
    if w.refund_ledger_entry_id:
        return w

    w.status = "failed"
    w.failure_reason = reason

    role = None
    if w.ledger_entry_id:
        try:
            role = _normalize_ledger_role(w.ledger_entry.role)
        except (AttributeError, KeyError, ValueError):
            role = None
    ledger_role = role or _infer_ledger_role_for_user(w.user)

    refund_entry = _create_ledger_entry(
        user=w.user,
        sale=None,
        role=ledger_role,
        entry_type="credit",
        amount=w.amount,
        notes=f"Release hold for failed withdrawal {w.id}",
    )
    w.refund_ledger_entry = refund_entry
    w.save(update_fields=["status", "failure_reason", "refund_ledger_entry"])

    transaction.on_commit(lambda: increment("payments.payout.failed_total", tags={"strategy": w.strategy}))
    logger.warning(
        "payments.withdrawal.failed",
        extra={
            "request_id": "",
            "idempotency_key": w.idempotency_key or "",
            "withdrawal_id": str(w.id),
            "provider_ref": w.paystack_transfer_ref or w.paystack_transfer_code or "",
            "reason": reason,
        },
    )
    return w


@transaction.atomic
def mark_withdrawal_reversed(withdrawal: Withdrawal, reason: str):
    w = Withdrawal.objects.select_for_update().select_related("user", "ledger_entry").get(pk=withdrawal.pk)
    if w.status == "reversed" or w.refund_ledger_entry_id:
        return w
    if w.status not in ("complete", "processing"):
        return w

    w.status = "reversed"
    w.failure_reason = f"Provider reversed: {reason}"

    role = None
    if w.ledger_entry_id:
        try:
            role = _normalize_ledger_role(w.ledger_entry.role)
        except (AttributeError, KeyError, ValueError):
            role = None
    ledger_role = role or _infer_ledger_role_for_user(w.user)

    refund_entry = _create_ledger_entry(
        user=w.user,
        sale=None,
        role=ledger_role,
        entry_type="credit",
        amount=w.amount,
        notes=f"Refund for reversed withdrawal {w.id}",
    )
    w.refund_ledger_entry = refund_entry
    w.save(update_fields=["status", "failure_reason", "refund_ledger_entry"])

    transaction.on_commit(lambda: increment("payments.payout.reversed_total", tags={"strategy": w.strategy}))
    logger.warning(
        "payments.withdrawal.reversed",
        extra={
            "request_id": "",
            "idempotency_key": w.idempotency_key or "",
            "withdrawal_id": str(w.id),
            "provider_ref": w.paystack_transfer_ref or w.paystack_transfer_code or "",
            "reason": reason,
        },
    )
    return w
