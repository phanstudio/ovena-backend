from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from payments.models import PaystackWebhookLog, Sale, Withdrawal
from payments.observability.metrics import increment, observe_ms
from payments.payouts.services import mark_withdrawal_failed, mark_withdrawal_paid
from menu.payment_handlers import order_fail, order_update

logger = logging.getLogger(__name__)

TRANSFER_EVENTS = {"transfer.success", "transfer.failed", "transfer.reversed"}


def _load_body(payload_bytes: bytes, parsed_body: dict[str, Any] | None) -> dict[str, Any]:
    if parsed_body is not None:
        return parsed_body
    if not payload_bytes:
        return {}
    return json.loads(payload_bytes.decode("utf-8"))


def _verify_signature(payload_bytes: bytes, signature: str) -> bool:
    computed = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), payload_bytes, hashlib.sha512).hexdigest()
    return hmac.compare_digest(computed, signature or "")


def _event_keys(body: dict[str, Any], payload_bytes: bytes) -> tuple[str, str, str, str]:
    event_type = body.get("event", "unknown")
    data = body.get("data", {})
    ref = data.get("reference") or data.get("transfer_code", "")
    event_id = str(data.get("id") or "")
    event_hash = hashlib.sha256(payload_bytes or b"{}").hexdigest()
    return event_type, ref, event_id, event_hash


def _find_payment_withdrawal(reference: str, transfer_code: str) -> Withdrawal | None:
    return Withdrawal.objects.filter(paystack_transfer_ref=reference).first() or Withdrawal.objects.filter(paystack_transfer_code=transfer_code).first()


def _reconcile_driver_withdrawal(transfer_reference: str, transfer_status: str, reason: str = "") -> None:
    try:
        from driver_api.tasks import reconcile_paystack_webhook
    except Exception:
        return
    reconcile_paystack_webhook(transfer_reference=transfer_reference, transfer_status=transfer_status, reason=reason)


def _sync_driver_withdrawal_from_linked_payment(payment_withdrawal: Withdrawal, transfer_status: str, reason: str = "") -> bool:
    driver_withdrawal = getattr(payment_withdrawal, "driver_withdrawal", None)
    if not driver_withdrawal:
        return False

    try:
        from driver_api.services import mark_withdrawal_failed as driver_mark_failed
        from driver_api.services import mark_withdrawal_paid as driver_mark_paid
    except Exception:
        return False

    if transfer_status == "success":
        driver_mark_paid(driver_withdrawal)
    else:
        driver_mark_failed(driver_withdrawal, reason=reason or "Paystack marked transfer as failed", manual=False)
    return True


def _record_webhook_lag(body: dict[str, Any], event_type: str) -> None:
    data = body.get("data", {})
    raw_time = data.get("paid_at") or data.get("createdAt") or data.get("created_at") or data.get("transferred_at")
    if not raw_time:
        return
    event_time = parse_datetime(str(raw_time))
    if not event_time:
        return
    if timezone.is_naive(event_time):
        event_time = timezone.make_aware(event_time, timezone.utc)
    lag_ms = max((timezone.now() - event_time).total_seconds() * 1000.0, 0.0)
    observe_ms("payments.webhook.processing_lag_ms", lag_ms, tags={"event": event_type})


def process_event(body: dict[str, Any]) -> None:
    event = body.get("event")
    data = body.get("data", {})

    if event == "charge.success":
        order_update(data)
        ref = data.get("reference")
        sale = Sale.objects.filter(paystack_reference=ref).first()
        if sale:
            sale.status = "in_escrow"
            sale.save(update_fields=["status", "updated_at"])
        return
    
    elif event == "charge.failed":
        order_fail(data)
        return 

    if event in TRANSFER_EVENTS:
        reference = data.get("reference", "")
        transfer_code = data.get("transfer_code", "")
        reason = data.get("gateway_response") or data.get("failure_reason") or "Transfer failed"

        payment_withdrawal = _find_payment_withdrawal(reference=reference, transfer_code=transfer_code)
        transfer_status = "success" if event == "transfer.success" else "failed"
        driver_synced_via_link = False

        if payment_withdrawal:
            if event == "transfer.success":
                mark_withdrawal_paid(payment_withdrawal)
            else:
                mark_withdrawal_failed(payment_withdrawal, reason=reason)
            driver_synced_via_link = _sync_driver_withdrawal_from_linked_payment(
                payment_withdrawal=payment_withdrawal,
                transfer_status=transfer_status,
                reason=reason,
            )

        if not driver_synced_via_link:
            _reconcile_driver_withdrawal(
                transfer_reference=reference or transfer_code,
                transfer_status=transfer_status,
                reason=reason,
            )
        return

    logger.info("[WEBHOOK] Unhandled event: %s", event)


def handle_paystack_webhook(
    *,
    payload_bytes: bytes,
    signature: str,
    parsed_body: dict[str, Any] | None = None,
    transfer_only: bool = False,
    request_id: str = "",
) -> tuple[int, str]:
    try:
        body = _load_body(payload_bytes=payload_bytes, parsed_body=parsed_body)
    except Exception:
        return 400, "Invalid JSON"

    event_type, ref, event_id, event_hash = _event_keys(body=body, payload_bytes=payload_bytes)
    if transfer_only and event_type not in TRANSFER_EVENTS:
        return 200, "Ignored event"

    is_valid = _verify_signature(payload_bytes=payload_bytes, signature=signature)

    increment("payments.webhook.received_total", tags={"event": event_type})
    _record_webhook_lag(body=body, event_type=event_type)

    logger.info(
        "payments.webhook.received",
        extra={
            "request_id": request_id,
            "idempotency_key": "",
            "withdrawal_id": "",
            "provider_ref": ref,
            "event_type": event_type,
            "event_id": event_id,
        },
    )

    try:
        webhook_log, created = PaystackWebhookLog.objects.get_or_create(
            event_hash=event_hash,
            defaults={
                "event_type": event_type,
                "event_id": event_id,
                "paystack_reference": ref,
                "payload": body,
                "signature_valid": is_valid,
            },
        )
    except IntegrityError:
        webhook_log = PaystackWebhookLog.objects.filter(event_hash=event_hash).first()
        created = False

    if not created and webhook_log and webhook_log.processed:
        increment("payments.webhook.replay_total", tags={"event": event_type})
        logger.info(
            "payments.webhook.replay",
            extra={
                "request_id": request_id,
                "idempotency_key": "",
                "withdrawal_id": "",
                "provider_ref": ref,
                "event_id": event_id,
            },
        )
        return 200, "Webhook already processed"

    if not is_valid:
        if webhook_log and not webhook_log.signature_valid:
            webhook_log.error_reason = "Invalid signature"
            webhook_log.save(update_fields=["error_reason"])
        increment("payments.webhook.invalid_signature_total", tags={"event": event_type})
        logger.warning(
            "payments.webhook.invalid_signature",
            extra={
                "request_id": request_id,
                "idempotency_key": "",
                "withdrawal_id": "",
                "provider_ref": ref,
                "event_id": event_id,
            },
        )
        return 400, "Invalid webhook signature"

    try:
        process_event(body)
        if webhook_log:
            webhook_log.processed = True
            webhook_log.processed_at = timezone.now()
            webhook_log.error_reason = ""
            webhook_log.save(update_fields=["processed", "processed_at", "error_reason"])

        increment("payments.webhook.processed_total", tags={"event": event_type})
        logger.info(
            "payments.webhook.processed",
            extra={
                "request_id": request_id,
                "idempotency_key": "",
                "withdrawal_id": "",
                "provider_ref": ref,
                "event_id": event_id,
            },
        )
    except Exception as exc:
        logger.error("[WEBHOOK] Error processing %s: %s", event_type, exc)
        if webhook_log:
            webhook_log.error_reason = str(exc)
            webhook_log.save(update_fields=["error_reason"])
        increment("payments.webhook.error_total", tags={"event": event_type})
        logger.error(
            "payments.webhook.error",
            extra={
                "request_id": request_id,
                "idempotency_key": "",
                "withdrawal_id": "",
                "provider_ref": ref,
                "event_id": event_id,
                "reason": str(exc),
            },
        )

    return 200, "Webhook processed"
