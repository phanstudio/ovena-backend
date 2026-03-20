from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from payments.integrations.paystack.client import PaystackClient
from payments.models import User, UserAccount, Withdrawal
from payments.observability.metrics import increment
from payments.services.split_calculator import _create_ledger_entry, get_ledger_balance

logger = logging.getLogger(__name__)

MINIMUM_BY_ROLE = {
    "driver": int(getattr(settings, "MIN_WITHDRAWAL_DRIVER", 100000)),
    "business_owner": int(getattr(settings, "MIN_WITHDRAWAL_BUSINESS", 200000)),
    "referral": int(getattr(settings, "MIN_WITHDRAWAL_REFERRAL", 50000)),
}

DAILY_WITHDRAWAL_LIMIT_COUNT = int(getattr(settings, "DAILY_WITHDRAWAL_LIMIT_COUNT", 5))
DAILY_WITHDRAWAL_LIMIT_AMOUNT = int(getattr(settings, "DAILY_WITHDRAWAL_LIMIT_AMOUNT_KOBO", 50_000_000))
WITHDRAWAL_COOLDOWN_HOURS = int(getattr(settings, "WITHDRAWAL_COOLDOWN_HOURS", 2))

STRATEGY_BATCH = Withdrawal.STRATEGY_BATCH
STRATEGY_REALTIME = Withdrawal.STRATEGY_REALTIME

LEDGER_ROLE_ALIASES = {
    "businessadmin": "business_owner",
}


@dataclass
class WithdrawalDecision:
    eligible: bool
    checks: dict
    minimum_amount_kobo: int
    available_balance_kobo: int


paystack_client = PaystackClient()


def _ledger_role_for_user(user: User) -> str:
    return LEDGER_ROLE_ALIASES.get(user.role, user.role)


def _pending_total(user) -> int:
    result = Withdrawal.objects.filter(user=user, status="pending_batch").aggregate(total=Sum("amount"))
    return result["total"] or 0


def _coerce_strategy(strategy: str | None) -> str:
    value = (strategy or STRATEGY_BATCH).lower().strip()
    if value not in {STRATEGY_BATCH, STRATEGY_REALTIME}:
        raise ValueError("Invalid payout strategy. Use 'batch' or 'realtime'.")
    return value


def get_balance_summary(user_id):
    user = User.objects.get(id=user_id)
    balance = get_ledger_balance(user)
    pending = _pending_total(user)
    available = balance - pending
    minimum = MINIMUM_BY_ROLE.get(_ledger_role_for_user(user), 0)
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


def evaluate_eligibility(user: User, amount_kobo: int) -> WithdrawalDecision:
    ledger_role = _ledger_role_for_user(user)
    minimum = MINIMUM_BY_ROLE.get(ledger_role)
    if minimum is None:
        return WithdrawalDecision(False, {"role_eligible": False}, 0, 0)

    balance = get_ledger_balance(user)
    pending = _pending_total(user)
    available = balance - pending

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_qs = Withdrawal.objects.filter(
        user=user,
        status__in=["pending_batch", "processing", "complete"],
        requested_at__gte=today_start,
    )
    daily_count = today_qs.count()
    daily_amount = today_qs.aggregate(total=Sum("amount"))["total"] or 0

    last_complete = Withdrawal.objects.filter(user=user, status="complete").order_by("-completed_at").first()
    cooldown_ok = True
    if last_complete and last_complete.completed_at:
        cooldown_ok = (now - last_complete.completed_at) >= timedelta(hours=WITHDRAWAL_COOLDOWN_HOURS)

    # Provider details are stored on the payment-specific UserAccount extension.
    account = UserAccount.objects.filter(user=user).first()
    checks = {
        "recipient_ready": bool(account and account.paystack_recipient_code),
        "role_eligible": True,
        "minimum_amount": amount_kobo >= minimum,
        "sufficient_balance": available >= amount_kobo,
        "cooldown_ok": cooldown_ok,
        "daily_count_ok": daily_count < DAILY_WITHDRAWAL_LIMIT_COUNT,
        "daily_amount_ok": daily_amount + amount_kobo <= DAILY_WITHDRAWAL_LIMIT_AMOUNT,
    }
    return WithdrawalDecision(
        eligible=all(checks.values()),
        checks=checks,
        minimum_amount_kobo=minimum,
        available_balance_kobo=available,
    )


@transaction.atomic
def create_withdrawal_request(
    user_id: str,
    amount_kobo: int,
    idempotency_key: str,
    strategy: str | None = None,
    request_id: str | None = None,
):
    user = User.objects.select_for_update().get(id=user_id)
    strategy_value = _coerce_strategy(strategy)

    existing = Withdrawal.objects.select_for_update().filter(user=user, idempotency_key=idempotency_key).first()
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

    decision = evaluate_eligibility(user=user, amount_kobo=amount_kobo)
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

    hold_entry = _create_ledger_entry(
        user=user,
        sale=None,
        role=_ledger_role_for_user(user),
        entry_type="debit",
        amount=-amount_kobo,
        notes="Hold for withdrawal request",
    )

    # Snapshot the payout recipient details from the UserAccount (if present).
    account = UserAccount.objects.filter(user=user).first()
    recipient_code = account.paystack_recipient_code if account else ""

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


@transaction.atomic
def process_withdrawal_request(withdrawal: Withdrawal):
    """Legacy alias kept for compatibility. Delegates to strategy executors."""
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

    _create_ledger_entry(
        user=withdrawal.user,
        sale=None,
        role=_ledger_role_for_user(withdrawal.user),
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

