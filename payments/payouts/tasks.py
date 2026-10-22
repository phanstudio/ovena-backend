import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from payments.integrations.paystack.client import PaystackClient
from payments.integrations.paystack.errors import PaystackRequestError
from payments.models import Withdrawal, UserAccount
from payments.payouts.services import (
    execute_batch,
    execute_realtime,
    mark_withdrawal_failed,
    mark_withdrawal_paid,
    mark_withdrawal_reversed,
)

logger = logging.getLogger(__name__)


@shared_task(
    name="payments.payouts.execute_realtime",
    time_limit=60,
    soft_time_limit=45,
)
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
    w = execute_realtime(withdrawal)
    return w.status if hasattr(w, "status") else withdrawal.status


@shared_task(
    name="payments.payouts.execute_batch",
    time_limit=180,
    soft_time_limit=150,
)
def execute_batch_payouts():
    return execute_batch()


# Backward compatibility alias used by existing callers.
@shared_task(name="payments.payouts.process_withdrawal")
def process_withdrawal(withdrawal_id: str):
    return execute_realtime_withdrawal(withdrawal_id)


@shared_task(name="payments.payouts.retry_pending_withdrawals")
def retry_pending_withdrawals():
    queued = 0
    qs = Withdrawal.objects.filter(
        status="pending_batch",
        strategy=Withdrawal.STRATEGY_REALTIME,
        is_flagged=False,
        retry_count__lt=F("max_retries"),
    )
    for withdrawal in qs:
        Withdrawal.objects.filter(id=withdrawal.id).update(retry_count=F("retry_count") + 1)
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

    qs = Withdrawal.objects.filter(
        Q(status="processing"),
        Q(processed_at__lt=cutoff) | Q(processed_at__isnull=True),
    ).select_related("user")

    for withdrawal in qs.iterator(chunk_size=100):
        transfer_ref = withdrawal.paystack_transfer_ref
        transfer_code = withdrawal.paystack_transfer_code
        lookup_key = transfer_code or transfer_ref

        if not lookup_key:
            skipped += 1
            logger.warning(
                "payments.withdrawal.reconcile.stuck_no_reference",
                extra={"withdrawal_id": str(withdrawal.id), "user_id": str(withdrawal.user_id)},
            )
            continue

        try:
            if transfer_ref:
                ps = paystack_client.verify_transfer(transfer_ref).get("data", {})
            else:
                ps = paystack_client.fetch_transfer(transfer_code).get("data", {})
        except Exception as exc:
            errors += 1
            logger.warning(
                "payments.withdrawal.reconcile.fetch_failed",
                extra={
                    "withdrawal_id": str(withdrawal.id),
                    "user_id": str(withdrawal.user_id),
                    "provider_ref": lookup_key,
                    "reason": str(exc),
                },
            )
            continue

        try:
            status = (ps.get("status") or "").lower().strip()
            if status == "success":
                mark_withdrawal_paid(withdrawal)
                reconciled += 1
            elif status == "reversed":
                reason = ps.get("failure_reason") or ps.get("gateway_response") or "Paystack marked transfer as reversed"
                mark_withdrawal_reversed(withdrawal, reason)
                reconciled += 1
            elif status in {"failed", "rejected"}:
                reason = ps.get("failure_reason") or ps.get("gateway_response") or "Paystack marked transfer as failed"
                mark_withdrawal_failed(withdrawal, reason)
                reconciled += 1
            else:
                skipped += 1
        except Exception as exc:
            errors += 1
            logger.error(
                "payments.withdrawal.reconcile.mark_failed",
                extra={
                    "withdrawal_id": str(withdrawal.id),
                    "reason": str(exc),
                },
            )

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


@shared_task(
    name="payments.payouts.ensure_paystack_recipient_for_driver",
    autoretry_for=(PaystackRequestError,),
    retry_backoff=True,
    max_retries=3,
    time_limit=60,
    soft_time_limit=45,
)
def ensure_paystack_recipient_for_driver(driver_id: int):
    try:
        from accounts.models import DriverProfile
        from accounts.models.driver import DriverBankAccount
    except ImportError:
        return "missing-models"

    with transaction.atomic():
        driver = DriverProfile.objects.filter(id=driver_id).select_related("user").first()
        if not driver:
            return "missing-driver"

        bank = DriverBankAccount.objects.select_for_update().filter(driver=driver).first()
        if not bank or not bank.is_verified:
            return "bank-not-verified"

        if bank.paystack_recipient_code:
            return bank.paystack_recipient_code

        payload = {
            "type": "nuban",
            "name": bank.bank_account_name,
            "account_number": bank.bank_account_number,
            "bank_code": bank.bank_code,
            "currency": "NGN",
        }
        client = PaystackClient()
        recipient = client.create_transfer_recipient(payload).get("data", {})
        code = recipient.get("recipient_code", "")
        if not code:
            return "missing-recipient-code"
        bank.paystack_recipient_code = code
        bank.save(update_fields=["paystack_recipient_code", "updated_at"])
        return code


@shared_task(
    name="payments.payouts.ensure_paystack_recipient_for_business_admin",
    autoretry_for=(PaystackRequestError,),
    retry_backoff=True,
    max_retries=3,
    time_limit=60,
    soft_time_limit=45,
)
def ensure_paystack_recipient_for_business_admin(business_admin_id: int):
    try:
        from accounts.models import BusinessAdmin, BusinessPayoutAccount
    except ImportError:
        return "missing-models"

    with transaction.atomic():
        admin = BusinessAdmin.objects.filter(id=business_admin_id).select_related("user", "business").first()
        if not admin or not admin.business_id:
            return "missing-business-admin"

        payout = BusinessPayoutAccount.objects.select_for_update().filter(business=admin.business).first()
        if not payout:
            return "missing-payout-account"

        if payout.paystack_recipient_code:
            return payout.paystack_recipient_code

        if not payout.bank_code or not payout.bank_account_number or not payout.bank_account_name:
            return "incomplete-payout-account"

        payload = {
            "type": "nuban",
            "name": payout.bank_account_name,
            "account_number": payout.bank_account_number,
            "bank_code": payout.bank_code,
            "currency": "NGN",
        }
        client = PaystackClient()
        recipient = client.create_transfer_recipient(payload).get("data", {})
        code = recipient.get("recipient_code", "")
        if not code:
            return "missing-recipient-code"

        payout.paystack_recipient_code = code
        payout.save(update_fields=["paystack_recipient_code", "updated_at"])
        return code


@shared_task(
    name="payments.payouts.ensure_paystack_recipient_for_user_accounts",
    autoretry_for=(PaystackRequestError,),
    retry_backoff=True,
    max_retries=3,
    time_limit=60,
    soft_time_limit=45,
)
def ensure_paystack_recipient_for_user_accounts(user_account_id: int):
    with transaction.atomic():
        account = UserAccount.objects.select_for_update().filter(id=user_account_id).first()
        if not account:
            return "missing-payout-account"

        if account.paystack_recipient_code:
            return account.paystack_recipient_code

        if not account.bank_code or not account.bank_account_number or not account.bank_account_name:
            return "incomplete-payout-account"

        payload = {
            "type": "nuban",
            "name": account.bank_account_name,
            "account_number": account.bank_account_number,
            "bank_code": account.bank_code,
            "currency": "NGN",
        }

        client = PaystackClient()
        recipient = client.create_transfer_recipient(payload).get("data", {})
        code = recipient.get("recipient_code", "")
        if not code:
            return "missing-recipient-code"

        account.paystack_recipient_code = code
        account.save(update_fields=["paystack_recipient_code", "updated_at"])
        return code
