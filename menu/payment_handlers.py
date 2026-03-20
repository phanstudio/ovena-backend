import logging

from django.utils import timezone

from .models import Order, OrderEvent
from .websocket_utils import notify_payment_completed, broadcast_to_order_group

logger = logging.getLogger(__name__)


def order_update(data: dict) -> bool:
    reference = data.get("reference")
    if not reference:
        return False

    amount = data.get("amount")
    status_msg = data.get("status")

    logger.info("Payment webhook received: %s - %s", reference, status_msg)

    order = (
        Order.objects.select_related("branch", "orderer")
        .filter(payment_reference=reference)
        .first()
    )
    if not order:
        logger.error("Order not found for payment reference: %s", reference)
        return False

    if order.status == "preparing":
        logger.info("Payment already processed for order %s", order.id)
        return True

    if order.status in ["confirmed", "payment_pending"]:
        old_status = order.status
        order.status = "preparing"
        order.payment_completed_at = timezone.now()
        order.save(update_fields=["status", "payment_completed_at", "last_modified_at"])

        OrderEvent.objects.create(
            order=order,
            event_type="payment_completed",
            actor_type="system",
            old_status=old_status,
            new_status="preparing",
            metadata={
                "reference": reference,
                "amount": amount,
                "payment_method": data.get("channel"),
            },
        )

        notify_payment_completed(order)
        logger.info("Order %s (ref: %s) marked as preparing", order.id, reference)
        return True

    return False


def order_fail(data: dict) -> bool:
    reference = data.get("reference")
    if not reference:
        return False

    logger.warning("Payment failed: %s", reference)

    order = Order.objects.filter(payment_reference=reference).first()
    if not order:
        return False

    OrderEvent.objects.create(
        order=order,
        event_type="payment_failed",
        actor_type="system",
        metadata={
            "reference": reference,
            "reason": data.get("gateway_response"),
        },
    )

    broadcast_to_order_group(
        order.id,
        {
            "type": "order.payment_failed",
            "message": "Payment failed. Please try again.",
            "reason": data.get("gateway_response"),
        },
    )
    return True
