"""views.py - DRF API endpoints"""
import logging

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from payments.idempotency import IdempotencyConflictError, begin_idempotent_request, save_idempotent_response
from payments.models import Withdrawal
from payments.services.sale_service import complete_service, initialize_sale, process_refund
from payments.payouts.services import create_withdrawal_request, get_balance_summary
from payments.payouts.tasks import process_withdrawal
from payments.webhooks.paystack import handle_paystack_webhook, process_event

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initialize_sale_view(request):
    """POST /api/sales/initialize/"""
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return Response({"error": "Idempotency-Key header is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        row, has_response = begin_idempotent_request(
            scope="sale_initialize",
            actor_id=str(request.user.id),
            key=idempotency_key,
            payload=request.data,
        )
        if has_response:
            return Response(row.response_snapshot, status=status.HTTP_200_OK)

        data = request.data
        result = initialize_sale(
            payer_id=str(request.user.id),
            driver_id=data.get("driver_id"),
            business_owner_id=data["business_owner_id"],
            amount_kobo=int(data["amount_kobo"]),
            metadata=data.get("metadata", {}),
        )
        save_idempotent_response(row, result)
        return Response(result, status=status.HTTP_201_CREATED)
    except IdempotencyConflictError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
    except Exception as exc:
        logger.error(f"initialize_sale error: {exc}")
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def complete_service_view(request, sale_id):
    """POST /api/sales/<sale_id>/complete/"""
    try:
        result = complete_service(sale_id)
        return Response(result)
    except Exception as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refund_sale_view(request, sale_id):
    """POST /api/sales/<sale_id>/refund/"""
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return Response({"error": "Idempotency-Key header is required"}, status=status.HTTP_400_BAD_REQUEST)

    reason = request.data.get("reason", "Refund requested")
    payload = {"sale_id": str(sale_id), "reason": reason}

    try:
        row, has_response = begin_idempotent_request(
            scope="refund_request",
            actor_id=str(request.user.id),
            key=idempotency_key,
            payload=payload,
        )
        if has_response:
            return Response(row.response_snapshot, status=status.HTTP_200_OK)

        result = process_refund(sale_id, reason)
        save_idempotent_response(row, result)
        return Response(result)
    except IdempotencyConflictError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
    except Exception as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def balance_view(request):
    """GET /api/wallet/balance/"""
    role = getattr(request, "query_params", {}).get("role") if hasattr(request, "query_params") else None
    if role:
        try:
            return Response(get_balance_summary(str(request.user.id), role=role))
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(get_balance_summary(str(request.user.id)))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def request_withdrawal_view(request):
    """POST /api/wallet/withdraw/"""
    amount_kobo = request.data.get("amount_kobo")
    idempotency_key = request.headers.get("Idempotency-Key")
    strategy = request.data.get("strategy", getattr(settings, "PAYMENTS_PAYOUT_STRATEGY_DEFAULT", "batch"))
    request_id = request.headers.get("X-Request-ID", "")
    role = request.data.get("role")

    if not amount_kobo:
        return Response({"error": "amount_kobo is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not idempotency_key:
        return Response({"error": "Idempotency-Key header is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        row, has_response = begin_idempotent_request(
            scope="withdrawal_request",
            actor_id=str(request.user.id),
            key=idempotency_key,
            payload=request.data,
        )
        if has_response:
            return Response(row.response_snapshot, status=status.HTTP_200_OK)

        kwargs = {
            "user_id": str(request.user.id),
            "amount_kobo": int(amount_kobo),
            "idempotency_key": idempotency_key,
            "strategy": strategy,
            "request_id": request_id,
        }
        if role:
            kwargs["role"] = role
        withdrawal, created = create_withdrawal_request(**kwargs)

        response_payload = {
            "success": True,
            "withdrawal_id": str(withdrawal.id),
            "amount_ngn": withdrawal.amount / 100,
            "status": withdrawal.status,
            "strategy": strategy,
            "message": "Withdrawal request queued" if created else "Duplicate request; existing withdrawal returned",
        }

        if strategy == "realtime":
            process_withdrawal.delay(str(withdrawal.id))
            response_payload["message"] = "Withdrawal request accepted and queued for realtime processing"

        save_idempotent_response(row, response_payload)
        return Response(response_payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
    except IdempotencyConflictError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def withdrawal_history_view(request):
    """GET /api/wallet/withdrawals/"""
    withdrawals = Withdrawal.objects.filter(user=request.user).order_by("-requested_at").values(
        "id", "amount", "status", "batch_date", "requested_at", "completed_at", "failure_reason"
    )
    return Response(list(withdrawals))


@api_view(["POST"])
@permission_classes([AllowAny])
def paystack_webhook_view(request):
    """POST /api/webhooks/paystack/"""
    status_code, detail = handle_paystack_webhook(
        payload_bytes=request.body or b"",
        signature=request.headers.get("X-Paystack-Signature", ""),
        parsed_body=request.data,
        transfer_only=False,
        request_id=request.headers.get("X-Request-ID", ""),
    )
    if status_code >= 400:
        logger.warning("[WEBHOOK] %s", detail)
    return Response({"detail": detail}, status=status_code)


def _process_webhook(body):
    """Compatibility proxy for tests/legacy callers."""
    process_event(body)




