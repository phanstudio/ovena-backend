from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce, TruncDay, TruncWeek
from django.utils import timezone

from accounts.models import DriverProfile
from menu.models import Order
from notifications.services import create_notification
from payments.eligibility import evaluate_eligibility
from payments.models import LedgerEntry, Withdrawal
from payments.payouts.services import create_withdrawal_request as create_payment_withdrawal
from payments.payouts.services import execute_realtime, get_balance_summary


def notify_driver(driver: DriverProfile, title: str, body: str, notification_type: str = "generic", payload=None):
    create_notification(
        user_id=driver.user_id,
        notification_type=notification_type,
        title=title,
        body=body,
        payload=payload or {},
    )


def _kobo_to_decimal(amount_kobo: int | None) -> Decimal:
    return (Decimal(amount_kobo or 0) / Decimal("100")).quantize(Decimal("0.01"))


def _decimal_to_kobo(amount: Decimal) -> int:
    return int((amount * Decimal("100")).quantize(Decimal("1")))


@dataclass
class WalletSnapshot:
    current_balance: Decimal
    available_balance: Decimal
    pending_balance: Decimal
    last_settled_at: datetime
    updated_at: datetime


def sync_wallet_from_ledger(driver: DriverProfile) -> WalletSnapshot:
    summary = get_balance_summary(str(driver.user_id), role="driver")
    now = timezone.now()
    available = _kobo_to_decimal(summary["available_balance_kobo"])
    pending = _kobo_to_decimal(summary["pending_withdrawal_kobo"])
    return WalletSnapshot(
        current_balance=available + pending,
        available_balance=available,
        pending_balance=pending,
        last_settled_at=now,
        updated_at=now,
    )


def ledger_credit_for_delivered_order(order: Order) -> LedgerEntry | None:
    if not order.driver_id or not order.sale_id:
        return None
    return (
        LedgerEntry.objects.filter(
            user=order.driver.user,
            sale_id=order.sale_id,
            role="driver",
            type="credit",
        )
        .order_by("created_at")
        .first()
    )


@dataclass
class WithdrawalDecision:
    eligible: bool
    checks: dict
    minimum_amount: Decimal
    max_amount: Decimal
    available_balance: Decimal


def evaluate_withdrawal_eligibility(driver: DriverProfile, amount: Decimal | None = None) -> WithdrawalDecision:
    amount_kobo = _decimal_to_kobo(amount or Decimal("0.00"))
    decision = evaluate_eligibility(user=driver.user, amount_kobo=amount_kobo, role="driver")
    return WithdrawalDecision(
        eligible=decision.eligible,
        checks=decision.checks,
        minimum_amount=_kobo_to_decimal(decision.minimum_amount_kobo),
        max_amount=_kobo_to_decimal(decision.available_balance_kobo),
        available_balance=_kobo_to_decimal(decision.available_balance_kobo),
    )


def create_withdrawal_request(driver: DriverProfile, amount: Decimal, idempotency_key: str):
    withdrawal, created = create_payment_withdrawal(
        user_id=str(driver.user_id),
        amount_kobo=_decimal_to_kobo(amount),
        idempotency_key=idempotency_key,
        role="driver",
        strategy=Withdrawal.STRATEGY_REALTIME,
    )
    if created:
        notify_driver(
            driver,
            "Withdrawal accepted",
            f"Your withdrawal request of {amount} has been accepted and is processing.",
            notification_type="withdrawal",
            payload={"withdrawal_id": str(withdrawal.id)},
        )
    return withdrawal, created


def process_withdrawal_request(withdrawal: Withdrawal):
    return execute_realtime(withdrawal)


def earnings_summary(driver: DriverProfile, start=None, end=None):
    qs = LedgerEntry.objects.filter(user=driver.user, role="driver")
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)

    total_earned_kobo = (
        qs.filter(type="credit")
        .exclude(notes__startswith="Release hold for failed withdrawal")
        .aggregate(total=Coalesce(Sum("amount"), 0))["total"]
        or 0
    )
    withdrawal_qs = Withdrawal.objects.filter(user=driver.user, status="complete")
    if start:
        withdrawal_qs = withdrawal_qs.filter(completed_at__gte=start)
    if end:
        withdrawal_qs = withdrawal_qs.filter(completed_at__lte=end)
    total_withdrawn_kobo = withdrawal_qs.aggregate(total=Coalesce(Sum("amount"), 0))["total"] or 0
    wallet = sync_wallet_from_ledger(driver)
    return {
        "total_earned": _kobo_to_decimal(total_earned_kobo),
        "total_withdrawn": _kobo_to_decimal(total_withdrawn_kobo),
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
    for order in completed.only("assigned_at", "delivered_at"):
        if order.assigned_at and order.delivered_at:
            duration_seconds.append((order.delivered_at - order.assigned_at).total_seconds())
    avg_duration = sum(duration_seconds) / len(duration_seconds) if duration_seconds else 0.0

    trunc_fn = TruncWeek if granularity == "week" else TruncDay
    trend_qs = (
        LedgerEntry.objects.filter(
            user=driver.user,
            role="driver",
            type="credit",
            created_at__gte=start,
            created_at__lte=end,
        )
        .annotate(bucket=trunc_fn("created_at"))
        .values("bucket")
        .annotate(total=Coalesce(Sum("amount"), 0))
        .order_by("bucket")
    )
    trend = [{"bucket": row["bucket"], "total": _kobo_to_decimal(row["total"])} for row in trend_qs]

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
