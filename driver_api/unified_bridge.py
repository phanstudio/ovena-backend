from __future__ import annotations

from uuid import uuid4

from django.utils import timezone

from driver_api.models import DriverWithdrawalRequest
from payments.models import UserAccount, Withdrawal as PaymentWithdrawal
from payments.observability.metrics import increment
from payments.payouts.services import execute_realtime as execute_payments_realtime


def _ensure_payments_withdrawal(withdrawal: DriverWithdrawalRequest, recipient_code: str) -> PaymentWithdrawal:
    if withdrawal.payment_withdrawal_id:
        existing = PaymentWithdrawal.objects.filter(id=withdrawal.payment_withdrawal_id).first()
        if existing:
            return existing

    payment_withdrawal_id = withdrawal.review_snapshot.get("payment_withdrawal_id")
    if payment_withdrawal_id:
        existing = PaymentWithdrawal.objects.filter(id=payment_withdrawal_id).first()
        if existing:
            withdrawal.payment_withdrawal = existing
            withdrawal.save(update_fields=["payment_withdrawal", "updated_at"])
            return existing

    user = withdrawal.driver.user

    # Ensure the payment-specific account exists and has the latest recipient code.
    account, _created = UserAccount.objects.get_or_create(user=user)
    if not account.paystack_recipient_code:
        account.paystack_recipient_code = recipient_code
        account.save(update_fields=["paystack_recipient_code", "updated_at"])

    payment_withdrawal = PaymentWithdrawal.objects.create(
        user=user,
        amount=int(withdrawal.amount * 100),
        status="pending_batch",
        strategy=PaymentWithdrawal.STRATEGY_REALTIME,
        idempotency_key=f"driver:{withdrawal.idempotency_key}",
        paystack_recipient_code=recipient_code,
    )
    withdrawal.payment_withdrawal = payment_withdrawal
    withdrawal.review_snapshot = {**withdrawal.review_snapshot, "payment_withdrawal_id": str(payment_withdrawal.id)}
    withdrawal.save(update_fields=["payment_withdrawal", "review_snapshot", "updated_at"])
    return payment_withdrawal


def process_driver_withdrawal_with_payments(withdrawal: DriverWithdrawalRequest, ensure_recipient_fn, max_retry_count: int):
    if withdrawal.status != DriverWithdrawalRequest.STATUS_APPROVED:
        return withdrawal

    bank = getattr(withdrawal.driver, "bank_account", None)
    if not bank or not bank.is_verified:
        withdrawal.mark_failed("Driver bank account is not verified", manual=True)
        increment("driver.withdrawal.manual_review_total")
        return withdrawal

    try:
        withdrawal.status = DriverWithdrawalRequest.STATUS_PROCESSING
        withdrawal.processed_at = timezone.now()
        withdrawal.save(update_fields=["status", "processed_at", "updated_at"])

        recipient_code = ensure_recipient_fn(bank)
        payment_withdrawal = _ensure_payments_withdrawal(withdrawal, recipient_code=recipient_code)
        execute_payments_realtime(payment_withdrawal)

        payment_withdrawal.refresh_from_db()
        withdrawal.transfer_ref = payment_withdrawal.paystack_transfer_ref or f"fallback-{uuid4().hex[:12]}"
        withdrawal.review_snapshot = {
            **withdrawal.review_snapshot,
            "payment_withdrawal_id": str(payment_withdrawal.id),
            "payment_transfer_code": payment_withdrawal.paystack_transfer_code,
        }
        withdrawal.save(update_fields=["transfer_ref", "review_snapshot", "updated_at"])
        return withdrawal
    except Exception as exc:
        withdrawal.retry_count += 1
        increment("driver.withdrawal.retry_total")
        manual = withdrawal.retry_count >= max_retry_count
        withdrawal.mark_failed(str(exc), manual=manual)
        if manual:
            increment("driver.withdrawal.manual_review_total")
        if not manual:
            withdrawal.status = DriverWithdrawalRequest.STATUS_APPROVED
            withdrawal.save(update_fields=["status", "retry_count", "updated_at"])
        return withdrawal


