import json
import hmac
import hashlib
import logging
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils import timezone
from .models import Order, OrderEvent
from .websocket_utils import notify_payment_completed

logger = logging.getLogger(__name__)


@csrf_exempt
def paystack_webhook(request):
    """
    Handle Paystack payment webhooks
    """
    # 1️⃣ Get raw body and signature
    payload = request.body
    paystack_signature = request.headers.get('x-paystack-signature')
    print('payment webhook received')

    # 2️⃣ Verify signature
    secret = settings.PAYSTACK_SECRET_KEY.encode()
    expected_signature = hmac.new(secret, payload, hashlib.sha512).hexdigest()

    if not hmac.compare_digest(expected_signature, paystack_signature or ""):
        logger.warning("Invalid Paystack webhook signature")
        return HttpResponse(status=401)

    # 3️⃣ Parse event data
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook payload")
        return HttpResponse(status=400)

    event_type = event.get('event')

    # 4️⃣ Handle payment success
    if event_type == "charge.success":
        data = event["data"]
        reference = data["reference"]
        amount = data["amount"]  # in kobo
        status_msg = data["status"]

        logger.info(f"Payment webhook received: {reference} - {status_msg}")

        try:
            order = Order.objects.select_related('branch', 'orderer').get(
                payment_reference=reference
            )
        except Order.DoesNotExist:
            logger.error(f"Order not found for payment reference: {reference}")
            return HttpResponse(status=404)

        # Check if already processed
        if order.status == "preparing":
            logger.info(f"Payment already processed for order {order.id}")
            return JsonResponse({"status": "already_processed"}, status=200)

        # Update order status
        if order.status in ["confirmed", "payment_pending"]:
            old_status = order.status
            order.status = "preparing"
            order.payment_completed_at = timezone.now()
            order.save(update_fields=["status", "payment_completed_at", "last_modified_at"])

            # Log event
            OrderEvent.objects.create(
                order=order,
                event_type='payment_completed',
                actor_type='system',
                old_status=old_status,
                new_status='preparing',
                metadata={
                    'reference': reference,
                    'amount': amount,
                    'payment_method': data.get('channel'),
                }
            )

            # 🔥 Broadcast payment success via WebSocket
            notify_payment_completed(order)

            logger.info(f"✅ Order {order.id} (ref: {reference}) marked as preparing")

            return JsonResponse({"status": "success"}, status=200)

    # 5️⃣ Handle payment failure
    elif event_type == "charge.failed":
        data = event["data"]
        reference = data["reference"]

        logger.warning(f"Payment failed: {reference}")

        try:
            order = Order.objects.get(payment_reference=reference)
            
            # Log event
            OrderEvent.objects.create(
                order=order,
                event_type='payment_failed',
                actor_type='system',
                metadata={
                    'reference': reference,
                    'reason': data.get('gateway_response')
                }
            )

            # Notify customer
            from .websocket_utils import broadcast_to_order_group
            broadcast_to_order_group(order.id, {
                'type': 'order.payment_failed',
                'message': 'Payment failed. Please try again.',
                'reason': data.get('gateway_response')
            })

        except Order.DoesNotExist:
            pass

        return JsonResponse({"status": "payment_failed"}, status=200)

    # Unknown event type
    logger.info(f"Received unknown webhook event: {event_type}")
    return JsonResponse({"status": "received"}, status=200)