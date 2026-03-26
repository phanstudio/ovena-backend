from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework import serializers as s
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from drf_spectacular.utils import extend_schema, inline_serializer  # type: ignore

from accounts.models import (
    Branch,
    BranchOperatingHours,
    Business,
    BusinessAdmin,
    BusinessCerd,
    BusinessOnboardStatus,
    BusinessPayoutAccount,
)
from accounts.serializers import InS, OpS
from addresses.utils import checkset_location
from authflow.authentication import CustomBAdminAuth
from authflow.permissions import IsBusinessAdmin
from payments.idempotency import IdempotencyConflictError, begin_idempotent_request, save_idempotent_response
from payments.models import Withdrawal
from payments.payouts.services import create_withdrawal_request, get_balance_summary
from payments.payouts.tasks import process_withdrawal


@extend_schema(
    responses=OpS.OnboardResponseSerializer,
)
class BuisnnessOnboardingStatusView(APIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def get(self, request):
        status_row: BusinessOnboardStatus = BusinessOnboardStatus.objects.filter(admin=request.user.business_admin).first()

        if not status_row:
            data = {
                "admin_id": request.user.id,
                "onboarding_step": 0,
                "is_onboarding_complete": False,
            }
        else:
            data = {
                "admin_id": status_row.admin.id,
                "onboarding_step": status_row.onboarding_step,
                "is_onboarding_complete": status_row.is_onboarding_complete,
            }
        response_data = OpS.OnboardResponseSerializer(data)
        return Response(response_data.data, status=status.HTTP_200_OK)


@extend_schema(
    responses={201: inline_serializer("Phase2Response", fields={
        "details": s.CharField(),
        "business_id": s.CharField(),
    })}
)
class RestaurantPhase1RegisterView(GenericAPIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]
    serializer_class = InS.RestaurantPhase1Serializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        user = request.user

        with transaction.atomic():
            restaurant = Business.objects.create(
                business_name=vd["business_name"],
                business_type=vd["business_type"],
                country=vd["country"],
                business_address=vd["business_address"],
                email=vd["email"],
                phone_number=vd["phone_number"],
            )
            BusinessCerd.objects.create(business=restaurant)
            user.set_password(vd["password"])
            user.save()

            business_admin = BusinessAdmin.objects.get(user=user)
            business_admin.business = restaurant
            business_admin.save()
            BusinessOnboardStatus.objects.filter(admin=business_admin).update(onboarding_step=1)

        return Response(
            {"detail": "Business registered. Proceed to onboarding.", "business_id": restaurant.id},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    responses={200: inline_serializer("Phase1Response", fields={
        "details": s.CharField(),
    })}
)
class RestaurantPhase2OnboardingView(GenericAPIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]
    serializer_class = InS.RestaurantPhase2Serializer

    def post(self, request):
        user = request.user

        try:
            admin = user.business_admin
        except BusinessAdmin.DoesNotExist:
            return Response({"detail": "Not a restaurant admin."}, status=status.HTTP_403_FORBIDDEN)

        restaurant: Business = admin.business
        restaurant_cerds = admin.business.cerd

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        with transaction.atomic():
            restaurant_cerds.registered_business_name = vd.get("registered_business_name", restaurant.business_name)
            restaurant_cerds.bn_number = vd.get("bn_number", "")
            restaurant_cerds.rc_number = vd.get("rc_number", "")
            restaurant_cerds.tax_identification_number = vd.get("tax_identification_number", "")
            restaurant_cerds.business_type = vd.get("business_type", restaurant.business_type)
            restaurant_cerds.doc_type = vd.get("doc_type", "")

            if "business_image" in request.FILES:
                restaurant.business_image = request.FILES["business_image"]
            if "business_documents" in request.FILES:
                restaurant_cerds.business_doc = request.FILES["business_documents"]

            restaurant.onboarding_complete = True
            restaurant_cerds.save()
            restaurant.save()
            onboarding_status: BusinessOnboardStatus = BusinessOnboardStatus.objects.get(admin=admin)
            onboarding_status.onboarding_step = 2
            onboarding_status.save()

            payment_data = vd.get("payment", {})
            if payment_data:
                BusinessPayoutAccount.objects.update_or_create(
                    business=restaurant,
                    defaults={
                        "bank_name": payment_data["bank"],
                        "bank_code": payment_data.get("bank_code", ""),
                        "account_number": payment_data["account_number"],
                        "account_name": payment_data["account_name"],
                        "bvn": payment_data["bvn"][-4:],
                    },
                )

            branches_data = vd.get("branches", [])
            for branch_data in branches_data:
                branch = Branch.objects.create(
                    business=restaurant,
                    name=branch_data["name"],
                    address=branch_data.get("address", "unknown"),
                    location=checkset_location(branch_data),
                    delivery_method=branch_data.get("delivery_method", "instant"),
                    pre_order_open_period=branch_data.get("pre_order_open_period"),
                    final_order_time=branch_data.get("final_order_time"),
                )

                hours_data = branch_data.get("operating_hours", [])
                BranchOperatingHours.objects.bulk_create([
                    BranchOperatingHours(
                        branch=branch,
                        day=h["day"],
                        open_time=h["open_time"],
                        close_time=h["close_time"],
                        is_closed=h.get("is_closed", False),
                    )
                    for h in hours_data
                ])

        return Response({"detail": "Onboarding complete."}, status=status.HTTP_200_OK)


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
