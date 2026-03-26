import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from payments.integrations.paystack.client import PaystackClient
from payments.models import UserAccount, Withdrawal
from payments.payouts.services import execute_batch, execute_realtime, mark_withdrawal_failed, mark_withdrawal_paid

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


@shared_task(name="payments.payouts.reconcile_stale_processing_withdrawals")
def reconcile_stale_processing_withdrawals():
    hours = int(getattr(settings, "PAYMENTS_STALE_WITHDRAWAL_HOURS", 6))
    cutoff = timezone.now() - timedelta(hours=hours)
    paystack_client = PaystackClient()

    reconciled = 0
    skipped = 0
    errors = 0

    qs = Withdrawal.objects.filter(status="processing", processed_at__lt=cutoff)
    for withdrawal in qs.select_related("user"):
        transfer_code = withdrawal.paystack_transfer_code or withdrawal.paystack_transfer_ref
        if not transfer_code:
            skipped += 1
            continue
        try:
            ps = paystack_client.fetch_transfer(transfer_code).get("data", {})
        except Exception as exc:
            errors += 1
            logger.warning(
                "payments.withdrawal.reconcile.fetch_failed",
                extra={
                    "withdrawal_id": str(withdrawal.id),
                    "user_id": str(withdrawal.user_id),
                    "provider_ref": transfer_code,
                    "reason": str(exc),
                },
            )
            continue

        status = (ps.get("status") or "").lower().strip()
        if status == "success":
            mark_withdrawal_paid(withdrawal)
            _sync_driver_withdrawal_if_linked(withdrawal, "success", "")
            reconciled += 1
        elif status in {"failed", "reversed"}:
            reason = ps.get("failure_reason") or ps.get("gateway_response") or "Paystack marked transfer as failed"
            mark_withdrawal_failed(withdrawal, reason)
            _sync_driver_withdrawal_if_linked(withdrawal, "failed", reason)
            reconciled += 1
        else:
            skipped += 1

    logger.info(
        "payments.withdrawal.reconcile.stale_complete",
        extra={
            "hours": hours,
            "reconciled": reconciled,
            "skipped": skipped,
            "errors": errors,
        },
    )
    return f"reconciled={reconciled} skipped={skipped} errors={errors}"


def _sync_driver_withdrawal_if_linked(withdrawal: Withdrawal, status: str, reason: str):
    driver_withdrawal = getattr(withdrawal, "driver_withdrawal", None)
    if not driver_withdrawal:
        return
    try:
        from driver_api.services import mark_withdrawal_failed as driver_mark_failed
        from driver_api.services import mark_withdrawal_paid as driver_mark_paid
    except Exception:
        return
    if status == "success":
        driver_mark_paid(driver_withdrawal)
    else:
        driver_mark_failed(driver_withdrawal, reason=reason or "Paystack marked transfer as failed", manual=False)


@shared_task(name="payments.payouts.ensure_paystack_recipient_for_driver")
def ensure_paystack_recipient_for_driver(driver_id: int):
    try:
        from accounts.models import DriverProfile
        from accounts.models.driver import DriverBankAccount
    except Exception:
        return "missing-models"

    driver = DriverProfile.objects.filter(id=driver_id).select_related("user").first()
    if not driver:
        return "missing-driver"
    bank = DriverBankAccount.objects.filter(driver=driver).first()
    if not bank or not bank.is_verified:
        return "bank-not-verified"

    account, _ = UserAccount.objects.get_or_create(user=driver.user)
    if account.paystack_recipient_code:
        return "already-set"

    payload = {
        "type": "nuban",
        "name": bank.account_name,
        "account_number": bank.account_number,
        "bank_code": bank.bank_code,
        "currency": "NGN",
    }
    client = PaystackClient()
    recipient = client.create_transfer_recipient(payload).get("data", {})
    code = recipient.get("recipient_code", "")
    if not code:
        return "missing-recipient-code"
    account.paystack_recipient_code = code
    account.bank_account_number = bank.account_number
    account.bank_code = bank.bank_code
    account.bank_account_name = bank.account_name
    account.save(update_fields=["paystack_recipient_code", "bank_account_number", "bank_code", "bank_account_name", "updated_at"])
    return code


@shared_task(name="payments.payouts.ensure_paystack_recipient_for_business_admin")
def ensure_paystack_recipient_for_business_admin(business_admin_id: int):
    try:
        from accounts.models import BusinessAdmin, BusinessPayoutAccount
    except Exception:
        return "missing-models"

    admin = BusinessAdmin.objects.filter(id=business_admin_id).select_related("user", "business").first()
    if not admin or not admin.business_id:
        return "missing-business-admin"

    payout = BusinessPayoutAccount.objects.filter(business=admin.business).first()
    if not payout:
        return "missing-payout-account"
    if not payout.bank_code or not payout.account_number or not payout.account_name:
        return "incomplete-payout-account"

    account, _ = UserAccount.objects.get_or_create(user=admin.user)
    account.bank_account_number = payout.account_number
    account.bank_code = payout.bank_code
    account.bank_account_name = payout.account_name

    payload = {
        "type": "nuban",
        "name": payout.account_name,
        "account_number": payout.account_number,
        "bank_code": payout.bank_code,
        "currency": "NGN",
    }
    client = PaystackClient()
    recipient = client.create_transfer_recipient(payload).get("data", {})
    code = recipient.get("recipient_code", "")
    if not code:
        account.save(update_fields=["bank_account_number", "bank_code", "bank_account_name", "updated_at"])
        return "missing-recipient-code"

    account.paystack_recipient_code = code
    account.save(update_fields=["paystack_recipient_code", "bank_account_number", "bank_code", "bank_account_name", "updated_at"])
    return code
