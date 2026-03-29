from django.conf import settings
from django.db import transaction
from rest_framework import status
# from rest_framework import serializers as s
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
# from drf_spectacular.utils import extend_schema, inline_serializer  # type: ignore

from accounts.models import (
    Branch,
    BranchOperatingHours,
    Business,
    BusinessAdmin,
    PrimaryAgent,
    # BusinessCerd,
    # BusinessOnboardStatus,
    BusinessPayoutAccount,
    User
)
from business_api.serializers import InS, OpS
from addresses.utils import checkset_location
from authflow.authentication import CustomBAdminAuth, CustomBStaffAuth
from authflow.permissions import IsBusinessAdmin, IsBusinessAgent
from payments.idempotency import IdempotencyConflictError, begin_idempotent_request, save_idempotent_response
from payments.models import Withdrawal
from payments.payouts.services import create_withdrawal_request, get_balance_summary
from payments.payouts.tasks import process_withdrawal
from rest_framework.pagination import LimitOffsetPagination
from accounts.serializers import InS as acInS
from drf_spectacular.utils import extend_schema # type: ignore

class businessLimitOffsetPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100

class BaseBuisAdminAPIView(GenericAPIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def get_buisnessadmn(self, request) -> BusinessAdmin:
        profile = request.user.business_admin
        if not profile:
            profile = get_object_or_404(BusinessAdmin, user=request.user)
        return profile

@extend_schema(responses={200: OpS.BuisnessResponse},)
class BranchCreateUpdateView(BaseBuisAdminAPIView):
    serializer_class = acInS.BranchInputSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch_data = serializer.validated_data
        buisness_admin = self.get_buisnessadmn(request)
        
        # Branches + operating hours
        branch = Branch.objects.create(
            business_id=buisness_admin.business.id,
            name=branch_data["name"],
            address=branch_data.get("address", "unknown"),
            location=checkset_location(branch_data),
            delivery_method=branch_data.get("delivery_method", "instant"),
            pre_order_open_period=branch_data.get("pre_order_open_period"),
            final_order_time=branch_data.get("final_order_time"),
        )

        hours_data = branch_data.get("operating_hours", [])
        BranchOperatingHours.objects.bulk_create(
            [
                BranchOperatingHours(
                    branch=branch,
                    day=h["day"],
                    open_time=h["open_time"],
                    close_time=h["close_time"],
                    is_closed=h.get("is_closed", False),
                )
                for h in hours_data
            ], 
        )

        return Response({"detail": "branch created."}, status=status.HTTP_201_CREATED)
    
    @extend_schema(
        request=InS.BranchInputSerializer,
    )
    def put(self, request):
        serializer = InS.BranchInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch_data = serializer.validated_data
        buisness_admin = self.get_buisnessadmn(request)

        update_data = {
            k: v for k, v in branch_data.items()
            if k not in ["id", "latitude", "longitude"]
        }

        if "latitude" in branch_data and "longitude" in branch_data:
            update_data["location"] = checkset_location(branch_data)

        
        updated = Branch.objects.filter(
            business_id=buisness_admin.business.id,
            id=branch_data["id"]
        ).update(**update_data)

        if not updated:
            return Response({"detail": "Branch not found"}, status=404)
        
        return Response({"detail": "branch updated."}, status=status.HTTP_200_OK)

class BranchListView(BaseBuisAdminAPIView):
    pagination_class = businessLimitOffsetPagination

    def get(self, request):
        buisness_admin = self.get_buisnessadmn(request)
        qs = Branch.objects.filter(business=buisness_admin.business.id).order_by("-created_at")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            {"detail": "Branches", "data": OpS.BranchlistSerializer(page, many=True).data}
        )

@extend_schema(responses={200: OpS.BuisnessResponse},)
class StaffRevokeView(BaseBuisAdminAPIView):
    serializer_class = InS.StaffRevokedSerializer
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        PrimaryAgent.objects.filter(id = vd["agent_id"]).update(revoked=vd["revoked"])
        return Response({"detail": f"agent {'revoked' if vd["revoked"] else 'Unrevoked'}"})

@extend_schema(responses=OpS.PrimaryAgentBranchSerializer)
class StaffListView(BaseBuisAdminAPIView):
    pagination_class = businessLimitOffsetPagination

    def get(self, request):
        buisness_admin = self.get_buisnessadmn(request)

        qs = (
            PrimaryAgent.objects
            .select_related("branch", "user")
            .filter(branch__business=buisness_admin.business)
            .order_by("-created_at")
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)

        serializer = OpS.PrimaryAgentBranchSerializer(page, many=True)
        return paginator.get_paginated_response({
            "detail": "Primary agents",
            "data": serializer.data
        })

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
        return Response({"detail": "User updated."})

def resolve_branch(request, branch_id=None):
    user = request.user

    actor_type = request.actor_type

    # Admin path
    if actor_type == "admin":
        if not branch_id:
            raise PermissionDenied("branch_id required for admin")

        branch = Branch.objects.filter(
            id=branch_id,
            business=user.business_admin.business
        ).first()

        if not branch:
            raise PermissionDenied("Invalid branch")

        return branch

    # Staff path
    if actor_type == "staff":
        agent = user.primaryagent

        if not agent or agent.revoked:
            raise PermissionDenied("Invalid staff account")

        return agent.branch

    raise PermissionDenied("Unauthorized")

# in the put we are changing everything
class BranchOperatingHoursView(APIView):
    authentication_classes = [
        CustomBStaffAuth, 
        CustomBAdminAuth
    ]
    permission_classes = [IsBusinessAgent]

    def get(self, request, branch_id=None):
        try:
            branch = resolve_branch(request, branch_id)
        except PermissionDenied as e:
            return Response({"detail": str(e)}, status=403)

        hours = BranchOperatingHours.objects.filter(branch=branch).order_by("day")
        serializer = acInS.BranchOperatingHoursSerializer(hours, many=True)
        return Response(serializer.data)

    def put(self, request, branch_id):
        try:
            branch = resolve_branch(request, branch_id)
        except PermissionDenied as e:
            return Response({"detail": str(e)}, status=403)

        serializer = acInS.BranchOperatingHoursSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            BranchOperatingHours.objects.filter(branch=branch).delete()
            BranchOperatingHours.objects.bulk_create([
                BranchOperatingHours(branch=branch, **h)
                for h in serializer.validated_data
            ])

        return Response({"detail": "Operating hours updated."})

# def get(self, request, branch_id=None):
#     branch = getattr(request, "branch", None)

#     if branch:
#         queryset = BranchOperatingHours.objects.filter(branch=branch)
#     else:
#         queryset = BranchOperatingHours.objects.filter(
#             branch__business=request.user.business_admin.business
#         )

#     serializer = InS.BranchOperatingHoursSerializer(queryset, many=True)
#     return Response(serializer.data)

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

        serializer = acInS.RestaurantPaymentSerializer(data=request.data)
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

# dashboard
# analysis
# support 
