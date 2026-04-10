from django.conf import settings
from datetime import datetime, timedelta
from django.db import transaction
from django.db.models import Avg, Count, DecimalField, Sum
from django.db.models.functions import Coalesce, TruncDay, TruncWeek, TruncHour
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from accounts.models import (
    Branch,
    BranchOperatingHours,
    BusinessAdmin,
    PrimaryAgent,
    BusinessPayoutAccount,
    User
)
from business_api.serializers import InS, OpS
from addresses.utils import checkset_location
from authflow.authentication import CustomBAdminAuth, CustomBusinessAgentsAuth
from authflow.permissions import IsBusinessAdmin, IsBusinessAgent
from payments.idempotency import IdempotencyConflictError, begin_idempotent_request, save_idempotent_response
from payments.models import LedgerEntry, Withdrawal
from payments.payouts.services import create_withdrawal_request, get_balance_summary
from payments.payouts.tasks import process_withdrawal
from rest_framework.pagination import LimitOffsetPagination
from accounts.serializers import InS as acInS
from drf_spectacular.utils import extend_schema # type: ignore
from menu.models import Order
from ratings.models import BranchRating
from abc import ABC

def _decimal_sum(field_name: str):
    return Coalesce(
        Sum(field_name),
        0,
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )

def _resolve_period(validated_data):
    range_key = validated_data.get("range", "30d")
    now = timezone.now()

    if range_key == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if range_key == "7d":
        return now - timedelta(days=7), now
    if range_key == "30d":
        return now - timedelta(days=30), now

    start = timezone.make_aware(datetime.combine(validated_data["from_date"], datetime.min.time()))
    end = timezone.make_aware(datetime.combine(validated_data["to_date"], datetime.max.time()))
    return start, end

def _delivered_orders_queryset(business_admin: BusinessAdmin):
    return (
        Order.objects
        .filter(branch__business=business_admin.business, status="delivered")
        .select_related("branch", "sale")
        .annotate(effective_at=Coalesce("delivered_at", "created_at"))
    )

def _filter_period(queryset, start, end, field_name="effective_at"):
    filters = {}
    if start is not None:
        filters[f"{field_name}__gte"] = start
    if end is not None:
        filters[f"{field_name}__lte"] = end
    return queryset.filter(**filters)

def _resolve_branch(request, branch_id=None):
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

def _select_trunc(start, end):
    delta = end - start

    if delta <= timedelta(days=1):
        return TruncHour

    if delta <= timedelta(days=60):
        return TruncDay

    return TruncWeek

class AbstractBuStAdBranchView(GenericAPIView, ABC):
    authentication_classes = [
        # CustomBStaffAuth,
        # CustomBAdminAuth
        CustomBusinessAgentsAuth
    ]
    permission_classes = [IsBusinessAgent]

    branch = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)

        branch_id = kwargs.get("branch_id")

        try:
            self.branch = _resolve_branch(request, branch_id)
        except PermissionDenied as e:
            raise PermissionDenied(str(e))

class businessLimitOffsetPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100

class BaseBuisAdminAPIView(GenericAPIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def get_buisnessadmn(self, request) -> BusinessAdmin:
        try:
            return request.user.business_admin
        except BusinessAdmin.DoesNotExist:
            return get_object_or_404(BusinessAdmin, user=request.user)

class BranchCreateUpdateView(BaseBuisAdminAPIView):
    serializer_class = acInS.BranchInputSerializer

    @extend_schema(
        request=acInS.BranchInputSerializer,
        responses={201: OpS.BuisnessResponse},
        description="Create a new branch with operating hours."
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch_data = serializer.validated_data
        buisness_admin = self.get_buisnessadmn(request)
        
        with transaction.atomic():
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
        responses={200: OpS.BuisnessResponse},
        description="Update branch details."
    )
    def patch(self, request):
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
        action = "revoked" if vd["revoked"] else "unrevoked"
        return Response({"detail": f"agent {action}"})

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

class BuisnessAdminUpdateView(BaseBuisAdminAPIView):
    serializer_class = InS.AdminUpdateSerializer
    def patch(self, request):
        user:User = request.user
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
    
        update_fields = []

        if "full_name" in vd:
            user.name = vd["full_name"]
            update_fields.append("name")

        if "phone_number" in vd:
            user.phone_number = vd["phone_number"]
            update_fields.append("phone_number")

        if "email" in vd:
            user.email = vd["email"]
            update_fields.append("email")

        if update_fields:
            user.save(update_fields=update_fields)

        return Response({"detail": "User updated."})

class BranchOperatingHoursView(AbstractBuStAdBranchView):
    @extend_schema(
        responses=acInS.BranchOperatingHoursSerializer,
        description="Update branch details."
    )
    def get(self, request, *args, **kwargs):
        hours = BranchOperatingHours.objects.filter(branch=self.branch).order_by("day")
        serializer = acInS.BranchOperatingHoursSerializer(hours, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=acInS.BranchOperatingHoursSerializer,
        responses={200: OpS.BuisnessResponse},
        description="Update branch details."
    )
    def put(self, request, *args, **kwargs):
        serializer = acInS.BranchOperatingHoursSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            BranchOperatingHours.objects.filter(branch=self.branch).delete()
            BranchOperatingHours.objects.bulk_create([
                BranchOperatingHours(branch=self.branch, **h)
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
        return Response(get_balance_summary(str(request.user.id), role="business_owner"))


class BusinessWalletWithdrawalView(APIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def post(self, request):
        business_admin = get_object_or_404(BusinessAdmin, user=request.user)
        amount_kobo = request.data.get("amount_kobo")
        idempotency_key = request.headers.get("Idempotency-Key")
        strategy = request.data.get("strategy", getattr(settings, "PAYMENTS_PAYOUT_STRATEGY_DEFAULT", "batch"))
        request_id = request.headers.get("X-Request-ID", "")
        transaction_pin = str(request.data.get("transaction_pin", "")).strip()

        if not amount_kobo:
            return Response({"error": "amount_kobo is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not idempotency_key:
            return Response({"error": "Idempotency-Key header is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not business_admin.has_transaction_pin:
            return Response({"error": "No transaction_pin saved"}, status=status.HTTP_400_BAD_REQUEST)
        if business_admin.has_transaction_pin and not business_admin.check_transaction_pin(transaction_pin):
            return Response({"error": "Valid transaction_pin is required"}, status=status.HTTP_400_BAD_REQUEST)

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


class BusinessDashboardView(BaseBuisAdminAPIView):
    serializer_class = InS.BusinessMetricsQuerySerializer

    def get(self, request):
        business_admin = self.get_buisnessadmn(request)
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        start, end = _resolve_period(serializer.validated_data)

        all_orders = _delivered_orders_queryset(business_admin)
        filtered_orders = _filter_period(all_orders, start, end)
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_orders = _filter_period(all_orders, today_start, timezone.now())

        all_totals = all_orders.aggregate(amount_made=_decimal_sum("grand_total"), sales_count=Count("id"))
        today_totals = today_orders.aggregate(today_sales=_decimal_sum("grand_total"), sales_count=Count("id"))
        shipment_totals = filtered_orders.aggregate(amount=_decimal_sum("grand_total"), count=Count("id"))

        data = {
            "username": request.user.name or request.user.email or request.user.phone_number or "",
            "today_sales": today_totals["today_sales"],
            "today_sales_count": today_totals["sales_count"],
            "amount_made": all_totals["amount_made"],
            "sales_count": all_totals["sales_count"],
            "total_shipment": {
                "filter": serializer.validated_data["range"],
                "count": shipment_totals["count"],
                "amount": shipment_totals["amount"],
            },
            "has_transaction_pin": business_admin.has_transaction_pin,
        }
        return Response({"detail": "Business dashboard", "data": data})


class BusinessStoreAnalysisView(BaseBuisAdminAPIView):
    serializer_class = InS.BusinessMetricsQuerySerializer

    def get(self, request):
        business_admin = self.get_buisnessadmn(request)
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        start, end = _resolve_period(serializer.validated_data)

        orders = _filter_period(_delivered_orders_queryset(business_admin), start, end)
        revenue_entries = _filter_period(
            LedgerEntry.objects.filter(user=request.user, role="business_owner", type="credit").exclude(
                notes__startswith="Release hold for failed withdrawal"
            ),
            start,
            end,
            field_name="created_at",
        )
        reviews = _filter_period(
            BranchRating.objects.filter(branch__business=business_admin.business),
            start,
            end,
            field_name="created_at",
        )

        total_used = "subtotal" # "grand_total"

        order_totals = orders.aggregate(
            # total_orders_amount=_decimal_sum("grand_total"),
            subtotal_amount=_decimal_sum("subtotal"),
            # delivery_amount=_decimal_sum("delivery_price"),
            discount_amount=_decimal_sum("discount_total"),
            orders_count=Count("id"),
        )
        revenue_kobo = revenue_entries.aggregate(total=Coalesce(Sum("amount"), 0))["total"] or 0
        reviews_totals = reviews.aggregate(
            average_rating=Coalesce(Avg("stars"), 0.0),
            reviews_count=Count("id"),
        )
        top_branch = (
            orders.values("branch_id", "branch__name")
            .annotate(
                total_orders=Count("id"),
                total_amount=_decimal_sum(total_used), # we need to add the discounts
            )
            .order_by("-total_amount", "-total_orders", "branch__name")
            .first()
        )
        _trunc = _select_trunc(start, end)
        trend = list(
            orders.annotate(bucket=_trunc("effective_at"))
            .values("bucket")
            .annotate(
                amount=_decimal_sum(total_used),
                orders_count=Count("id"),
            )
            .order_by("bucket")
        )

        data = {
            "filters": serializer.validated_data,
            "revenue_breakdown": {
                "total_revenue_kobo": revenue_kobo,
                "total_revenue_ngn": revenue_kobo / 100,
                # "total_orders_amount": order_totals["total_orders_amount"],
                "subtotal_amount": order_totals["subtotal_amount"],
                "total": order_totals["subtotal_amount"] + order_totals["discount_amount"],
                # "online_delivery_amount": order_totals["delivery_amount"],
                "discount_amount": order_totals["discount_amount"],
                "orders_count": order_totals["orders_count"],
            },
            "reviews": {
                "average_rating": round(float(reviews_totals["average_rating"] or 0), 2),
                "count": reviews_totals["reviews_count"],
            },
            "topseller_branch": {
                "branch_id": top_branch["branch_id"] if top_branch else None,
                "branch_name": top_branch["branch__name"] if top_branch else None,
                "orders_count": top_branch["total_orders"] if top_branch else 0,
                "amount": top_branch["total_amount"] if top_branch else 0,
            },
            "trend_revenue": [
                {
                    "date": row["bucket"],
                    "amount": row["amount"],
                    "orders_count": row["orders_count"],
                }
                for row in trend
            ],
        }
        return Response({"detail": "Store analysis", "data": data})


class BusinessTransactionPinView(BaseBuisAdminAPIView):
    serializer_class = InS.AdminTransactionPinSerializer

    def get(self, request):
        business_admin = self.get_buisnessadmn(request)
        return Response(
            {
                "detail": "Transaction pin status",
                "data": {
                    "has_transaction_pin": business_admin.has_transaction_pin,
                },
            }
        )

    def post(self, request):
        business_admin = self.get_buisnessadmn(request)
        serializer = self.get_serializer(data=request.data, context={"business_admin": business_admin})
        serializer.is_valid(raise_exception=True)
        business_admin.set_transaction_pin(serializer.validated_data["pin"])
        business_admin.save(update_fields=["transaction_pin_hash"])
        return Response(
            {
                "detail": "Transaction pin saved",
                "data": {
                    "has_transaction_pin": True,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class BusinessTransactionHistoryView(BaseBuisAdminAPIView):
    serializer_class = InS.BusinessTransactionHistoryQuerySerializer
    pagination_class = businessLimitOffsetPagination

    def get(self, request):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        start, end = _resolve_period(vd)

        items = []
        transaction_type = vd.get("transaction_type", "all")
        withdrawal_status = vd.get("withdrawal_status", "").strip()

        if transaction_type in {"all", "credit", "debit", "reversal"}:
            ledger_qs = _filter_period(
                LedgerEntry.objects.filter(user=request.user, role="business_owner"),
                start,
                end,
                field_name="created_at",
            )
            if transaction_type != "all":
                ledger_qs = ledger_qs.filter(type=transaction_type)

            for entry in ledger_qs.order_by("-created_at"):
                amount_kobo = int(entry.amount)
                items.append(
                    {
                        "id": str(entry.id),
                        "source": "ledger",
                        "transaction_type": entry.type,
                        "status": "posted",
                        "amount_kobo": abs(amount_kobo),
                        "signed_amount_kobo": amount_kobo,
                        "amount_ngn": abs(amount_kobo) / 100,
                        "reference": str(entry.sale_id) if entry.sale_id else "",
                        "description": entry.notes,
                        "created_at": entry.created_at,
                    }
                )

        if transaction_type in {"all", "withdrawal"}:
            withdrawals = _filter_period(
                Withdrawal.objects.filter(user=request.user),
                start,
                end,
                field_name="requested_at",
            )
            if withdrawal_status:
                withdrawals = withdrawals.filter(status=withdrawal_status)

            for withdrawal in withdrawals.order_by("-requested_at"):
                amount_kobo = int(withdrawal.amount)
                items.append(
                    {
                        "id": str(withdrawal.id),
                        "source": "withdrawal",
                        "transaction_type": "withdrawal",
                        "status": withdrawal.status,
                        "amount_kobo": amount_kobo,
                        "signed_amount_kobo": -amount_kobo,
                        "amount_ngn": amount_kobo / 100,
                        "reference": withdrawal.paystack_transfer_ref or withdrawal.paystack_transfer_code or "",
                        "description": withdrawal.failure_reason or "Withdrawal request",
                        "created_at": withdrawal.requested_at,
                    }
                )

        items.sort(key=lambda item: item["created_at"], reverse=True)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(items, request)
        return paginator.get_paginated_response({"detail": "Transaction history", "data": page})

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