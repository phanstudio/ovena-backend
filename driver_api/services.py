from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.db.models import DecimalField, Q, Sum
from django.db.models.functions import Coalesce, TruncDay, TruncWeek
from django.utils import timezone

from payments.integrations.paystack.client import PaystackClient
from payments.observability.metrics import increment

from accounts.models import DriverBankAccount, DriverProfile
from driver_api.models import (
    DriverLedgerEntry,
    DriverNotification,
    DriverWallet,
    DriverWithdrawalRequest,
    SupportTicket,
)
from menu.models import Order
from driver_api.unified_bridge import process_driver_withdrawal_with_payments


MIN_WITHDRAWAL = Decimal("1000.00")
MAX_RETRY_COUNT = 3
WITHDRAWAL_COOLDOWN_HOURS = 2
DAILY_WITHDRAWAL_LIMIT_COUNT = 5
DAILY_WITHDRAWAL_LIMIT_AMOUNT = Decimal("500000.00")


def notify_driver(driver: DriverProfile, title: str, body: str, notification_type: str = "generic", payload=None):
    DriverNotification.objects.create(
        driver=driver,
        notification_type=notification_type,
        title=title,
        body=body,
        payload_json=payload or {},
    )


def get_or_create_wallet(driver: DriverProfile) -> DriverWallet:
    wallet, _ = DriverWallet.objects.get_or_create(driver=driver)
    return wallet


def sync_wallet_from_ledger(driver: DriverProfile) -> DriverWallet:
    wallet = get_or_create_wallet(driver)
    aggregates = DriverLedgerEntry.objects.filter(driver=driver, status=DriverLedgerEntry.STATUS_POSTED).aggregate(
        credit=Coalesce(
            Sum("amount", filter=Q(entry_type=DriverLedgerEntry.TYPE_CREDIT)),
            Decimal("0.00"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
        debit=Coalesce(
            Sum("amount", filter=Q(entry_type=DriverLedgerEntry.TYPE_DEBIT)),
            Decimal("0.00"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
        hold=Coalesce(
            Sum("amount", filter=Q(entry_type=DriverLedgerEntry.TYPE_HOLD)),
            Decimal("0.00"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
        release=Coalesce(
            Sum("amount", filter=Q(entry_type=DriverLedgerEntry.TYPE_RELEASE)),
            Decimal("0.00"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
    )
    current = aggregates["credit"] - aggregates["debit"]
    pending = aggregates["hold"] - aggregates["release"]
    available = current - pending
    wallet.current_balance = max(current, Decimal("0.00"))
    wallet.pending_balance = max(pending, Decimal("0.00"))
    wallet.available_balance = max(available, Decimal("0.00"))
    wallet.last_settled_at = timezone.now()
    wallet.save(update_fields=["current_balance", "pending_balance", "available_balance", "last_settled_at", "updated_at"])
    return wallet


def ledger_credit_for_delivered_order(order: Order) -> DriverLedgerEntry | None:
    if not order.driver_id or order.status != "delivered":
        return None
    source_id = str(order.id)
    existing = DriverLedgerEntry.objects.filter(
        driver=order.driver,
        source_type="order_delivery",
        source_id=source_id,
        entry_type=DriverLedgerEntry.TYPE_CREDIT,
    ).first()
    if existing:
        return existing

    amount = order.delivery_price or Decimal("0.00")
    if amount <= 0:
        return None
    entry = DriverLedgerEntry.objects.create(
        driver=order.driver,
        entry_type=DriverLedgerEntry.TYPE_CREDIT,
        amount=amount,
        source_type="order_delivery",
        source_id=source_id,
        status=DriverLedgerEntry.STATUS_POSTED,
        metadata={"order_number": order.order_number},
    )
    sync_wallet_from_ledger(order.driver)
    return entry


@dataclass
class WithdrawalDecision:
    eligible: bool
    checks: dict
    minimum_amount: Decimal
    max_amount: Decimal
    available_balance: Decimal


def evaluate_withdrawal_eligibility(driver: DriverProfile, amount: Decimal | None = None) -> WithdrawalDecision:
    wallet = sync_wallet_from_ledger(driver)
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    bank = getattr(driver, "bank_account", None)

    blocking_ticket = SupportTicket.objects.filter(
        driver=driver,
        status__in=[SupportTicket.STATUS_OPEN, SupportTicket.STATUS_IN_PROGRESS],
        is_blocking=True,
    ).exists()

    last_paid = (
        DriverWithdrawalRequest.objects.filter(driver=driver, status=DriverWithdrawalRequest.STATUS_PAID)
        .order_by("-paid_at")
        .first()
    )
    cooldown_ok = True
    if last_paid and last_paid.paid_at:
        cooldown_ok = (now - last_paid.paid_at) >= timedelta(hours=WITHDRAWAL_COOLDOWN_HOURS)

    today_withdrawals = DriverWithdrawalRequest.objects.filter(
        driver=driver,
        status__in=[
            DriverWithdrawalRequest.STATUS_REQUESTED,
            DriverWithdrawalRequest.STATUS_APPROVED,
            DriverWithdrawalRequest.STATUS_PROCESSING,
            DriverWithdrawalRequest.STATUS_PAID,
        ],
        created_at__gte=today_start,
    )
    daily_count = today_withdrawals.count()
    daily_amount = today_withdrawals.aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))
    )["total"]

    checks = {
        "bank_verified": bool(bank and bank.is_verified),
        "sufficient_balance": bool(amount is None or wallet.available_balance >= amount),
        "minimum_amount": bool(amount is None or amount >= MIN_WITHDRAWAL),
        "no_blocking_ticket": not blocking_ticket,
        "cooldown_ok": cooldown_ok,
        "daily_count_ok": daily_count < DAILY_WITHDRAWAL_LIMIT_COUNT,
        "daily_amount_ok": daily_amount < DAILY_WITHDRAWAL_LIMIT_AMOUNT,
    }
    eligible = all(checks.values())
    return WithdrawalDecision(
        eligible=eligible,
        checks=checks,
        minimum_amount=MIN_WITHDRAWAL,
        max_amount=wallet.available_balance,
        available_balance=wallet.available_balance,
    )


paystack_client = PaystackClient()


def _ensure_transfer_recipient(bank_account: DriverBankAccount):
    payload = {
        "type": "nuban",
        "name": bank_account.account_name,
        "account_number": bank_account.account_number,
        "bank_code": bank_account.bank_code,
        "currency": "NGN",
    }
    recipient = paystack_client.create_transfer_recipient(payload).get("data", {})
    return recipient.get("recipient_code", "")


def _initiate_transfer(recipient_code: str, amount: Decimal, reason: str):
    payload = {
        "source": "balance",
        "amount": int(amount * 100),
        "recipient": recipient_code,
        "reason": reason,
    }
    data = paystack_client.initiate_transfer(payload)
    transfer_data = data.get("data", {})
    return transfer_data.get("reference", ""), data


@transaction.atomic
def create_withdrawal_request(driver: DriverProfile, amount: Decimal, idempotency_key: str):
    existing = DriverWithdrawalRequest.objects.select_for_update().filter(
        driver=driver,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        return existing, False

    decision = evaluate_withdrawal_eligibility(driver=driver, amount=amount)
    bank = getattr(driver, "bank_account", None)
    bank_snapshot = {
        "bank_code": getattr(bank, "bank_code", ""),
        "bank_name": getattr(bank, "bank_name", ""),
        "account_number": getattr(bank, "account_number", ""),
        "account_name": getattr(bank, "account_name", ""),
        "verified": bool(bank and bank.is_verified),
    }
    status = DriverWithdrawalRequest.STATUS_APPROVED if decision.eligible else DriverWithdrawalRequest.STATUS_AUTO_REJECTED
    withdrawal = DriverWithdrawalRequest.objects.create(
        driver=driver,
        amount=amount,
        idempotency_key=idempotency_key,
        status=status,
        bank_snapshot=bank_snapshot,
        review_snapshot={"checks": decision.checks},
        approved_at=timezone.now() if decision.eligible else None,
        failure_reason="" if decision.eligible else "Eligibility checks failed",
    )

    if decision.eligible:
        DriverLedgerEntry.objects.create(
            driver=driver,
            entry_type=DriverLedgerEntry.TYPE_HOLD,
            amount=amount,
            source_type="withdrawal",
            source_id=str(withdrawal.id),
            status=DriverLedgerEntry.STATUS_POSTED,
            metadata={"phase": "hold"},
        )
        sync_wallet_from_ledger(driver)
        notify_driver(
            driver,
            "Withdrawal approved",
            f"Your withdrawal request of {amount} has been approved and is processing.",
            notification_type=DriverNotification.TYPE_WITHDRAWAL,
            payload={"withdrawal_id": withdrawal.id},
        )
    else:
        notify_driver(
            driver,
            "Withdrawal rejected",
            "Your withdrawal request did not pass eligibility checks.",
            notification_type=DriverNotification.TYPE_WITHDRAWAL,
            payload={"withdrawal_id": withdrawal.id, "checks": decision.checks},
        )

    return withdrawal, True


def process_withdrawal_request(withdrawal: DriverWithdrawalRequest):
    return process_driver_withdrawal_with_payments(
        withdrawal=withdrawal,
        ensure_recipient_fn=_ensure_transfer_recipient,
        max_retry_count=MAX_RETRY_COUNT,
    )


@transaction.atomic
def mark_withdrawal_paid(withdrawal: DriverWithdrawalRequest):
    if withdrawal.status == DriverWithdrawalRequest.STATUS_PAID:
        return withdrawal
    withdrawal.status = DriverWithdrawalRequest.STATUS_PAID
    withdrawal.paid_at = timezone.now()
    withdrawal.processed_at = timezone.now()
    withdrawal.save(update_fields=["status", "paid_at", "processed_at", "updated_at"])

    DriverLedgerEntry.objects.create(
        driver=withdrawal.driver,
        entry_type=DriverLedgerEntry.TYPE_DEBIT,
        amount=withdrawal.amount,
        source_type="withdrawal",
        source_id=str(withdrawal.id),
        status=DriverLedgerEntry.STATUS_POSTED,
        metadata={"phase": "debit"},
    )
    DriverLedgerEntry.objects.create(
        driver=withdrawal.driver,
        entry_type=DriverLedgerEntry.TYPE_RELEASE,
        amount=withdrawal.amount,
        source_type="withdrawal",
        source_id=str(withdrawal.id),
        status=DriverLedgerEntry.STATUS_POSTED,
        metadata={"phase": "release_hold"},
    )
    sync_wallet_from_ledger(withdrawal.driver)
    notify_driver(
        withdrawal.driver,
        "Withdrawal paid",
        f"Withdrawal of {withdrawal.amount} has been paid successfully.",
        notification_type=DriverNotification.TYPE_WITHDRAWAL,
        payload={"withdrawal_id": withdrawal.id},
    )
    return withdrawal


@transaction.atomic
def mark_withdrawal_failed(withdrawal: DriverWithdrawalRequest, reason: str, manual: bool = False):
    withdrawal.mark_failed(reason=reason, manual=manual)
    increment("driver.withdrawal.failed_total", tags={"manual": str(bool(manual)).lower()})
    if manual:
        increment("driver.withdrawal.manual_review_total")
    DriverLedgerEntry.objects.create(
        driver=withdrawal.driver,
        entry_type=DriverLedgerEntry.TYPE_RELEASE,
        amount=withdrawal.amount,
        source_type="withdrawal",
        source_id=str(withdrawal.id),
        status=DriverLedgerEntry.STATUS_POSTED,
        metadata={"phase": "release_on_failure"},
    )
    sync_wallet_from_ledger(withdrawal.driver)
    notify_driver(
        withdrawal.driver,
        "Withdrawal failed",
        reason,
        notification_type=DriverNotification.TYPE_WITHDRAWAL,
        payload={"withdrawal_id": withdrawal.id, "manual_review": manual},
    )
    return withdrawal


def earnings_summary(driver: DriverProfile, start=None, end=None):
    qs = DriverLedgerEntry.objects.filter(driver=driver, status=DriverLedgerEntry.STATUS_POSTED)
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)
    total_earned = qs.filter(entry_type=DriverLedgerEntry.TYPE_CREDIT).aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))
    )["total"]
    total_withdrawn = qs.filter(
        entry_type=DriverLedgerEntry.TYPE_DEBIT, source_type="withdrawal"
    ).aggregate(total=Coalesce(Sum("amount"), Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2)))["total"]
    wallet = sync_wallet_from_ledger(driver)
    return {
        "total_earned": total_earned,
        "total_withdrawn": total_withdrawn,
        "available_balance": wallet.available_balance,
        "pending_balance": wallet.pending_balance,
        "period_start": start,
        "period_end": end,
    }


def performance_metrics(driver: DriverProfile, start, end, granularity="day"):
    orders = Order.objects.filter(driver=driver, created_at__gte=start, created_at__lte=end)
    completed = orders.filter(status="delivered")
    assigned = orders.filter(status__in=["driver_assigned", "picked_up", "on_the_way", "delivered"])
    cancellations = orders.filter(status="cancelled")

    completed_count = completed.count()
    assigned_count = assigned.count()
    cancellation_count = cancellations.count()
    acceptance_rate = (completed_count / assigned_count * 100) if assigned_count else 0.0
    completion_rate = (completed_count / orders.count() * 100) if orders.exists() else 0.0
    cancellation_rate = (cancellation_count / orders.count() * 100) if orders.exists() else 0.0

    duration_seconds = []
    for o in completed.only("assigned_at", "delivered_at"):
        if o.assigned_at and o.delivered_at:
            duration_seconds.append((o.delivered_at - o.assigned_at).total_seconds())
    avg_duration = sum(duration_seconds) / len(duration_seconds) if duration_seconds else 0.0

    trunc_fn = TruncWeek if granularity == "week" else TruncDay
    trend_qs = (
        DriverLedgerEntry.objects.filter(
            driver=driver,
            status=DriverLedgerEntry.STATUS_POSTED,
            entry_type=DriverLedgerEntry.TYPE_CREDIT,
            created_at__gte=start,
            created_at__lte=end,
        )
        .annotate(bucket=trunc_fn("created_at"))
        .values("bucket")
        .annotate(total=Coalesce(Sum("amount"), Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2)))
        .order_by("bucket")
    )
    trend = [{"bucket": row["bucket"], "total": row["total"]} for row in trend_qs]

    return {
        "completed_deliveries": completed_count,
        "acceptance_rate": round(acceptance_rate, 2),
        "completion_rate": round(completion_rate, 2),
        "cancellation_rate": round(cancellation_rate, 2),
        "avg_delivery_duration_seconds": round(avg_duration, 2),
        "online_hours": 0.0,
        "active_hours": round(avg_duration * completed_count / 3600, 2),
        "earnings_trend": trend,
    }


def parse_range(range_key: str, from_date=None, to_date=None):
    now = timezone.now()
    if range_key == "7d":
        return now - timedelta(days=7), now
    if range_key == "30d":
        return now - timedelta(days=30), now
    if range_key == "90d":
        return now - timedelta(days=90), now
    if range_key == "custom" and from_date and to_date:
        start = timezone.make_aware(datetime.combine(from_date, datetime.min.time()))
        end = timezone.make_aware(datetime.combine(to_date, datetime.max.time()))
        return start, end
    return now - timedelta(days=30), now






