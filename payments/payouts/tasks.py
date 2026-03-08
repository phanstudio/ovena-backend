import logging

from celery import shared_task

from payments.models import Withdrawal
from payments.payouts.services import execute_batch, execute_realtime

logger = logging.getLogger(__name__)


@shared_task(name="payments.payouts.execute_realtime")
def execute_realtime_withdrawal(withdrawal_id: str):
    withdrawal = Withdrawal.objects.filter(id=withdrawal_id).select_related("user").first()
    if not withdrawal:
        logger.warning(
            "payments.withdrawal.realtime.task.missing",
            extra={
                "request_id": "",
                "idempotency_key": "",
                "withdrawal_id": str(withdrawal_id),
                "provider_ref": "",
            },
        )
        return "missing"
    execute_realtime(withdrawal)
    return withdrawal.status


@shared_task(name="payments.payouts.execute_batch")
def execute_batch_payouts():
    return execute_batch()


# Backward compatibility alias used by existing callers.
@shared_task(name="payments.payouts.process_withdrawal")
def process_withdrawal(withdrawal_id: str):
    return execute_realtime_withdrawal(withdrawal_id)


@shared_task(name="payments.payouts.retry_pending_withdrawals")
def retry_pending_withdrawals():
    queued = 0
    for withdrawal in Withdrawal.objects.filter(status="pending_batch", strategy=Withdrawal.STRATEGY_REALTIME):
        execute_realtime_withdrawal.delay(str(withdrawal.id))
        queued += 1

    logger.info(
        "payments.withdrawal.realtime.retry_queued",
        extra={
            "request_id": "",
            "idempotency_key": "",
            "withdrawal_id": "",
            "provider_ref": "",
            "queued": queued,
        },
    )
    return f"queued={queued}"
