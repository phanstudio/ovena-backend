from celery import shared_task
from django.utils import timezone

from driver_api.models import DriverWithdrawalRequest
from driver_api.services import mark_withdrawal_failed, mark_withdrawal_paid, process_withdrawal_request


@shared_task(name="driver_api.process_withdrawal")
def process_withdrawal(withdrawal_id: int):
    withdrawal = DriverWithdrawalRequest.objects.filter(id=withdrawal_id).select_related("driver").first()
    if not withdrawal:
        return "missing"
    process_withdrawal_request(withdrawal)
    return withdrawal.status


@shared_task(name="driver_api.retry_pending_withdrawals")
def retry_pending_withdrawals():
    qs = DriverWithdrawalRequest.objects.filter(
        status=DriverWithdrawalRequest.STATUS_APPROVED,
        needs_manual_review=False,
    )
    count = 0
    for withdrawal in qs:
        process_withdrawal.delay(withdrawal.id)
        count += 1
    return f"queued={count}"


def reconcile_paystack_webhook(transfer_reference: str, transfer_status: str, reason: str = ""):
    withdrawal = (
        DriverWithdrawalRequest.objects.filter(payment_withdrawal__paystack_transfer_ref=transfer_reference)
        .select_related("driver")
        .first()
        or DriverWithdrawalRequest.objects.filter(transfer_ref=transfer_reference).select_related("driver").first()
        or DriverWithdrawalRequest.objects.filter(review_snapshot__payment_withdrawal_id=transfer_reference)
        .select_related("driver")
        .first()
    )
    if not withdrawal:
        return None
    if transfer_status == "success":
        mark_withdrawal_paid(withdrawal)
    elif transfer_status in {"failed", "reversed"}:
        mark_withdrawal_failed(withdrawal, reason=reason or "Paystack marked transfer as failed", manual=False)
    return withdrawal
