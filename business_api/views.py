from django.conf import settings
from django.db import transaction
from rest_framework import status
# from rest_framework import serializers as s
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from django.shortcuts import get_object_or_404
# from rest_framework.generics import GenericAPIView
# from drf_spectacular.utils import extend_schema, inline_serializer  # type: ignore

from accounts.models import (
    Branch,
    BranchOperatingHours,
    # Business,
    BusinessAdmin,
    # BusinessCerd,
    # BusinessOnboardStatus,
    BusinessPayoutAccount,
    User
)
from business_api.serializers import InS
# , OpS
# from addresses.utils import checkset_location
from authflow.authentication import CustomBAdminAuth
from authflow.permissions import IsBusinessAdmin
from payments.idempotency import IdempotencyConflictError, begin_idempotent_request, save_idempotent_response
from payments.models import Withdrawal
from payments.payouts.services import create_withdrawal_request, get_balance_summary
from payments.payouts.tasks import process_withdrawal


class BaseBuisAdminAPIView(GenericAPIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def get_buisnessadmn(self, request) -> BusinessAdmin:
        profile = request.user.buisnessadmin
        if not profile:
            profile = get_object_or_404(BusinessAdmin, user=request.user)
        return profile



class BuisnessUpdateView(BaseBuisAdminAPIView):
    serializer_class = InS.AdminUpdateSerializer
    def put(self, request):
        user:User = request.user
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
    
        user.name = vd.get("full_name", user.name)
        user.phone_number = vd.get("phone_number", user.phone_number)
        user.email = vd.get("email", user.email)
        user.save()

class BranchOperatingHoursView(APIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def get(self, request, branch_id):
        user = request.user
        try:
            admin = user.business_admin
        except BusinessAdmin.DoesNotExist:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        branch = Branch.objects.filter(id=branch_id, business=admin.business).first()
        if not branch:
            return Response({"detail": "Branch not found."}, status=status.HTTP_404_NOT_FOUND)

        hours = BranchOperatingHours.objects.filter(branch=branch).order_by("day")
        serializer = InS.BranchOperatingHoursSerializer(hours, many=True)
        return Response(serializer.data)

    def put(self, request, branch_id):
        user = request.user
        try:
            admin = user.business_admin
        except BusinessAdmin.DoesNotExist:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        branch = Branch.objects.filter(id=branch_id, business=admin.business).first()
        if not branch:
            return Response({"detail": "Branch not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = InS.BranchOperatingHoursSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            BranchOperatingHours.objects.filter(branch=branch).delete()
            BranchOperatingHours.objects.bulk_create([
                BranchOperatingHours(branch=branch, **h)
                for h in serializer.validated_data
            ])

        return Response({"detail": "Operating hours updated."})


class RestaurantPaymentView(APIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def get(self, request):
        user = request.user
        try:
            admin = user.business_admin
        except BusinessAdmin.DoesNotExist:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        try:
            payment = admin.business.payout
        except BusinessPayoutAccount.DoesNotExist:
            return Response({"detail": "No payment info set."}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "bank": payment.bank_name,
                "bank_code": payment.bank_code,
                "account_number": payment.account_number,
                "account_name": payment.account_name,
                "bvn": payment.bvn or "",
            }
        )

    def put(self, request):
        user = request.user
        try:
            admin = user.business_admin
        except BusinessAdmin.DoesNotExist:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        serializer = InS.RestaurantPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        BusinessPayoutAccount.objects.update_or_create(
            business=admin.business,
            defaults={
                "bank_name": vd["bank"],
                "bank_code": vd.get("bank_code", ""),
                "account_number": vd["account_number"],
                "account_name": vd["account_name"],
                "bvn": vd["bvn"],
            },
        )
        return Response({"detail": "Payment info updated."})


class BusinessWalletBalanceView(APIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def get(self, request):
        return Response(get_balance_summary(str(request.user.id)))


class BusinessWalletWithdrawalView(APIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def post(self, request):
        amount_kobo = request.data.get("amount_kobo")
        idempotency_key = request.headers.get("Idempotency-Key")
        strategy = request.data.get("strategy", getattr(settings, "PAYMENTS_PAYOUT_STRATEGY_DEFAULT", "batch"))
        request_id = request.headers.get("X-Request-ID", "")

        if not amount_kobo:
            return Response({"error": "amount_kobo is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not idempotency_key:
            return Response({"error": "Idempotency-Key header is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            row, has_response = begin_idempotent_request(
                scope="business_withdrawal_request",
                actor_id=str(request.user.id),
                key=idempotency_key,
                payload=request.data,
            )
            if has_response:
                return Response(row.response_snapshot, status=status.HTTP_200_OK)

            withdrawal, created = create_withdrawal_request(
                user_id=str(request.user.id),
                amount_kobo=int(amount_kobo),
                idempotency_key=idempotency_key,
                strategy=strategy,
                request_id=request_id,
                role="business_owner"
            )

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


class BusinessWalletWithdrawalHistoryView(APIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def get(self, request):
        withdrawals = Withdrawal.objects.filter(user=request.user).order_by("-requested_at").values(
            "id", "amount", "status", "batch_date", "requested_at", "completed_at", "failure_reason"
        )
        return Response(list(withdrawals))
