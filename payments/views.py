"""views.py - DRF API endpoints"""
import logging

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.generics import GenericAPIView, ListAPIView

from payments.idempotency import IdempotencyConflictError, begin_idempotent_request, save_idempotent_response
from payments.models import Withdrawal
from payments.services.sale_service import complete_service, initialize_sale, process_refund
from payments.payouts.services import create_withdrawal_request, get_balance_summary
from payments.payouts.tasks import process_withdrawal
from payments.webhooks.paystack import handle_paystack_webhook, process_event

from payments.models import Bank
from payments.integrations.client import client
from common.pagination import PageNumberPagination
from .serializers import (
    BankSerializer,
    SaleInitializeSerializer,
    SaleRefundSerializer,
    WalletBalanceQuerySerializer,
    RequestWithdrawalSerializer,
    WithdrawalHistorySerializer,
    AdminReviewWithdrawalActionSerializer,
)
from admin_api.views import BaseAppAdminAPIView

logger = logging.getLogger(__name__)


class SaleInitializeView(GenericAPIView):
    """POST /api/sales/initialize/"""
    permission_classes = [IsAuthenticated]
    serializer_class = SaleInitializeSerializer

    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response({"error": "Idempotency-Key header is required"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data

        try:
            row, has_response = begin_idempotent_request(
                scope="sale_initialize",
                actor_id=str(request.user.id),
                key=idempotency_key,
                payload=request.data,
            )
            if has_response:
                return Response(row.response_snapshot, status=status.HTTP_200_OK)

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


class SaleCompleteView(GenericAPIView):
    """POST /api/sales/<sale_id>/complete/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, sale_id):
        try:
            result = complete_service(sale_id)
            return Response(result)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class SaleRefundView(GenericAPIView):
    """POST /api/sales/<sale_id>/refund/"""
    permission_classes = [IsAuthenticated]
    serializer_class = SaleRefundSerializer

    def post(self, request, sale_id):
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response({"error": "Idempotency-Key header is required"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        vd = serializer.validated_data

        reason = vd.get("reason", "Refund requested")
        responsible_party = vd.get("responsible_party", "business")
        responsible_party_reason = vd.get("responsible_party_reason", "")

        payload = {
            "sale_id": str(sale_id),
            "reason": reason,
            "responsible_party": responsible_party,
            "responsible_party_reason": responsible_party_reason,
        }

        try:
            row, has_response = begin_idempotent_request(
                scope="refund_request",
                actor_id=str(request.user.id),
                key=idempotency_key,
                payload=payload,
            )
            if has_response:
                return Response(row.response_snapshot, status=status.HTTP_200_OK)

            result = process_refund(
                sale_id,
                reason,
                responsible_party=responsible_party,
                responsible_party_reason=responsible_party_reason,
            )
            save_idempotent_response(row, result)
            return Response(result)
        except IdempotencyConflictError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class WalletBalanceView(GenericAPIView):
    """GET /api/wallet/balance/"""
    permission_classes = [IsAuthenticated]
    serializer_class = WalletBalanceQuerySerializer

    def get(self, request):
        serializer = self.get_serializer(data=request.query_params)
        role = None
        if serializer.is_valid():
            role = serializer.validated_data.get("role")
        if role:
            try:
                return Response(get_balance_summary(str(request.user.id), role=role))
            except ValueError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(get_balance_summary(str(request.user.id)))


class RequestWithdrawalView(GenericAPIView):
    """POST /api/wallet/withdraw/"""
    permission_classes = [IsAuthenticated]
    serializer_class = RequestWithdrawalSerializer

    def post(self, request):
        from accounts.services.roles import has_role
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response({"error": "Idempotency-Key header is required"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        vd = serializer.validated_data

        amount_kobo = vd["amount_kobo"]
        strategy = vd.get("strategy") or getattr(settings, "PAYMENTS_PAYOUT_STRATEGY_DEFAULT", "batch")
        request_id = request.headers.get("X-Request-ID", "")
        role = vd.get("role")

        # Role-based authorization guard
        if role == "driver" and not has_role(request, "driver"):
            return Response({"error": "User does not have driver authorization."}, status=status.HTTP_403_FORBIDDEN)
        if role == "business_owner" and not has_role(request, "business_admin"):
            return Response({"error": "User does not have business authorization."}, status=status.HTTP_403_FORBIDDEN)

        # Security Cooldown Guard
        from accounts.services.security_guards import (
            is_security_cooldown_active,
            is_pin_locked,
            record_failed_pin_attempt,
            clear_pin_attempts,
        )
        cooldown_active, rem_sec = is_security_cooldown_active(request.user)
        if cooldown_active:
            hours = max(1, rem_sec // 3600)
            return Response(
                {"error": f"Withdrawals are temporarily paused due to recent security updates on your account. Try again in {hours} hour(s)."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Customer Transaction PIN Guard
        if role == "customer":
            account = getattr(request.user, "payment_account", None)
            if not account or not account.has_transaction_pin:
                return Response(
                    {"error": "Transaction PIN not configured. Please set a transaction PIN before proceeding."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            pin = vd.get("transaction_pin") or request.headers.get("X-Transaction-PIN")
            if not pin:
                return Response({"error": "transaction_pin is required for customer withdrawals."}, status=status.HTTP_400_BAD_REQUEST)

            locked, rem_lock = is_pin_locked(request.user.id)
            if locked:
                mins = max(1, rem_lock // 60)
                return Response(
                    {"error": f"Transaction PIN is locked due to multiple failed attempts. Try again in {mins} minute(s)."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            if not account.check_transaction_pin(str(pin)):
                attempts = record_failed_pin_attempt(request.user.id, ip_address=request.META.get("REMOTE_ADDR"))
                rem = max(0, 5 - attempts)
                return Response({"error": f"Incorrect transaction PIN. {rem} attempt(s) remaining."}, status=status.HTTP_400_BAD_REQUEST)

            clear_pin_attempts(request.user.id)

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


class WithdrawalHistoryView(ListAPIView):
    """GET /api/wallet/withdrawals/"""
    permission_classes = [IsAuthenticated]
    serializer_class = WithdrawalHistorySerializer
    pagination_class = None

    def get_queryset(self):
        return Withdrawal.objects.filter(user=self.request.user).order_by("-requested_at")


class PaystackWebhookView(GenericAPIView):
    """POST /api/webhooks/paystack/"""
    permission_classes = [AllowAny]

    def post(self, request):
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


# Backward-compatible function aliases for legacy routers and test suites
initialize_sale_view = SaleInitializeView.as_view()
complete_service_view = SaleCompleteView.as_view()
refund_sale_view = SaleRefundView.as_view()
balance_view = WalletBalanceView.as_view()
request_withdrawal_view = RequestWithdrawalView.as_view()
withdrawal_history_view = WithdrawalHistoryView.as_view()
paystack_webhook_view = PaystackWebhookView.as_view()


def _process_webhook(body):
    """Compatibility proxy for tests/legacy callers."""
    process_event(body)


# Bank views
class SyncBanks(BaseAppAdminAPIView):
    def get(self, _request):
        try:
            country = "nigeria"
            banks_data = client.list_banks({"country": country, "currency": "NGN"})

            if not banks_data.get('status'):
                return Response({"detail": f'Sync failed: status failed'}, status=500)

            unique_banks = {}

            for b in banks_data["data"]:
                unique_banks[(country, b["code"])] = Bank(
                    country=country,
                    code=b["code"],
                    name=b["name"],
                    slug=b["slug"],
                    supports_transfer=b.get("supports_transfer", True),
                    active=b.get("active", True),
                )

            banks = list(unique_banks.values())

            Bank.objects.bulk_create(
                banks,
                update_conflicts=True,
                update_fields=[
                    "name",
                    "slug",
                    "supports_transfer",
                    "active",
                ],
                unique_fields=["code", "country"],
            )
        except Exception as e:
            return Response({"detail": f'Sync failed: {e}'}, status=500)

        return Response({"detail": 'Successfully synced banks.'})


class ListBanks(ListAPIView): # require an active profile
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    queryset = Bank.objects.all()
    serializer_class = BankSerializer


class AdminReviewWithdrawalView(BaseAppAdminAPIView):
    """
    Admin endpoint to review a customer withdrawal claim, audit the ledger hash chain,
    and resolve (approve_and_transfer, mark_paid, reject).
    """
    serializer_class = AdminReviewWithdrawalActionSerializer

    def get(self, request, withdrawal_id):
        from payments.services.ledger_audit import verify_user_ledger_chain_since_last_withdrawal

        withdrawal = Withdrawal.objects.filter(id=withdrawal_id).first()
        if not withdrawal:
            return Response({"error": "Withdrawal not found"}, status=status.HTTP_404_NOT_FOUND)

        is_valid, reason, failed_ids = verify_user_ledger_chain_since_last_withdrawal(withdrawal.user)

        return Response({
            "withdrawal_id": str(withdrawal.id),
            "user_id": str(withdrawal.user_id),
            "amount": withdrawal.amount,
            "status": withdrawal.status,
            "is_flagged": withdrawal.is_flagged,
            "flag_reason": withdrawal.flag_reason,
            "flagged_at": withdrawal.flagged_at,
            "hash_chain_valid": is_valid,
            "hash_chain_reason": reason,
            "failed_entry_ids": failed_ids,
        })

    def post(self, request, withdrawal_id):
        from payments.services.ledger_audit import (
            verify_user_ledger_chain_since_last_withdrawal,
            flag_withdrawal,
        )
        from payments.payouts.services import (
            execute_realtime,
            mark_withdrawal_paid,
            mark_withdrawal_failed,
        )

        withdrawal = Withdrawal.objects.filter(id=withdrawal_id).first()
        if not withdrawal:
            return Response({"error": "Withdrawal not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid action. Choose from 'approve_and_transfer', 'mark_paid', 'reject'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        action = serializer.validated_data["action"]

        if action in ["approve_and_transfer", "mark_paid"]:
            is_valid, reason, failed_ids = verify_user_ledger_chain_since_last_withdrawal(withdrawal.user)
            if not is_valid:
                flag_withdrawal(withdrawal, reason=reason, failed_entry_ids=failed_ids)
                return Response(
                    {"error": f"Approval blocked. Hash chain integrity verification failed: {reason}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if action == "approve_and_transfer":
                execute_realtime(withdrawal)
                return Response({"message": "Withdrawal approved and queued for transfer.", "status": withdrawal.status})
            else:
                mark_withdrawal_paid(withdrawal)
                return Response({"message": "Withdrawal marked paid.", "status": withdrawal.status})

        # Reject action
        reject_reason = serializer.validated_data.get("reason", "Admin rejected withdrawal claim")
        mark_withdrawal_failed(withdrawal, reason=reject_reason)
        return Response({"message": "Withdrawal rejected and ledger hold released.", "status": withdrawal.status})
