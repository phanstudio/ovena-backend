"""
withdrawal_service.py - withdrawal requests, balance checks, minimum enforcement
"""
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from payments.models import User, Withdrawal
from payments.services.split_calculator import _create_ledger_entry, get_ledger_balance

MINIMUM_BY_ROLE = {
    "driver": int(getattr(settings, "MIN_WITHDRAWAL_DRIVER", 100000)),
    "business_owner": int(getattr(settings, "MIN_WITHDRAWAL_BUSINESS", 200000)),
    "referral": int(getattr(settings, "MIN_WITHDRAWAL_REFERRAL", 50000)),
}


def get_pending_withdrawal_total(user) -> int:
    from django.db.models import Sum

    result = Withdrawal.objects.filter(user=user, status="pending_batch").aggregate(total=Sum("amount"))
    return result["total"] or 0


def get_balance_summary(user_id):
    user = User.objects.get(id=user_id)
    balance = get_ledger_balance(user)
    pending = get_pending_withdrawal_total(user)
    available = balance - pending
    minimum = MINIMUM_BY_ROLE.get(user.role, 0)

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


@transaction.atomic
def request_withdrawal(user_id, amount_kobo, idempotency_key):
    """
    Queue a withdrawal for tonight's batch.
    Creates a pending debit ledger entry to lock the balance.
    """
    user = User.objects.select_for_update().get(id=user_id)

    existing = Withdrawal.objects.select_for_update().filter(user=user, idempotency_key=idempotency_key).first()
    if existing:
        return {
            "success": True,
            "withdrawal_id": str(existing.id),
            "amount_ngn": existing.amount / 100,
            "message": "Duplicate request; existing withdrawal returned.",
            "estimated_arrival": existing.requested_at.isoformat(),
        }

    if not user.paystack_recipient_code:
        raise ValueError("Bank account not set up. Please add your bank details first.")

    minimum = MINIMUM_BY_ROLE.get(user.role)
    if minimum is None:
        raise ValueError(f"Role '{user.role}' is not eligible for withdrawals.")

    if amount_kobo < minimum:
        raise ValueError(f"Minimum withdrawal is NGN {minimum/100:.0f}. You requested NGN {amount_kobo/100:.0f}.")

    balance = get_ledger_balance(user)
    pending = get_pending_withdrawal_total(user)
    available = balance - pending

    if available < amount_kobo:
        raise ValueError(f"Insufficient balance. Available: NGN {available/100:.2f}, Requested: NGN {amount_kobo/100:.2f}")

    ledger_entry = _create_ledger_entry(
        user=user,
        sale=None,
        role=user.role,
        entry_type="debit",
        amount=-amount_kobo,
        notes="Withdrawal request queued for nightly batch",
    )

    withdrawal_ref = f"WDR_{str(user.id)[:8]}_{uuid.uuid4().hex[:8].upper()}"

    withdrawal = Withdrawal.objects.create(
        user=user,
        amount=amount_kobo,
        status="pending_batch",
        idempotency_key=idempotency_key,
        paystack_transfer_ref=withdrawal_ref,
        paystack_recipient_code=user.paystack_recipient_code,
        ledger_entry=ledger_entry,
    )

    tonight = timezone.now().replace(hour=23, minute=0, second=0, microsecond=0)

    return {
        "success": True,
        "withdrawal_id": str(withdrawal.id),
        "amount_ngn": amount_kobo / 100,
        "message": f"Withdrawal of NGN {amount_kobo/100:.2f} queued for tonight.",
        "estimated_arrival": tonight.isoformat(),
    }
