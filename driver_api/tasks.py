from celery import shared_task

from driver_api.services import process_withdrawal_request
from payments.models import Withdrawal


@shared_task(name="driver_api.process_withdrawal")
def process_withdrawal(withdrawal_id: str):
    withdrawal = Withdrawal.objects.filter(id=withdrawal_id).select_related("user").first()
    if not withdrawal:
        return "missing"
    process_withdrawal_request(withdrawal)
    return withdrawal.status


@shared_task(name="driver_api.retry_pending_withdrawals")
def retry_pending_withdrawals():
    qs = Withdrawal.objects.filter(status="pending_batch", strategy=Withdrawal.STRATEGY_REALTIME)
    count = 0
    for withdrawal in qs:
        process_withdrawal.delay(str(withdrawal.id))
        count += 1
    return f"queued={count}"
