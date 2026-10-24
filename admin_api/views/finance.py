from django.db.models import Sum
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.exceptions import NotFound

from payments.models import Withdrawal
from payments.payouts.services import mark_withdrawal_paid, mark_withdrawal_failed
from payments.payouts.tasks import (
    execute_batch_payouts,
    execute_realtime_withdrawal,
    retry_pending_withdrawals,
    reconcile_stale_processing_withdrawals,
)
from referrals.models import ReferralPayout
from referrals.serializers import ReferralPayoutSerializer
from referrals.services import verify_snapshot_integrity
from admin_api.models import AppAdmin
from admin_api.serializers import (
    AdminWithdrawalSerializer,
    AdminWithdrawalMarkFailedSerializer,
)
from .base import BaseAppAdminAPIView, _AppAdminRoleGuardMixin


class AdminWithdrawalListView(BaseAppAdminAPIView, ListAPIView):
    """
    GET /api/admin/withdrawals/
    Filter withdrawals by status, strategy, user_id, and date range.
    """
    serializer_class = AdminWithdrawalSerializer

    def get_queryset(self):
        qs = Withdrawal.objects.select_related("user", "ledger_entry").order_by(
            "-requested_at"
        )

        status_q = (self.request.query_params.get("status") or "").strip().lower()
        if status_q:
            qs = qs.filter(status=status_q)

        strategy = (self.request.query_params.get("strategy") or "").strip().lower()
        if strategy:
            qs = qs.filter(strategy=strategy)

        user_id = (self.request.query_params.get("user_id") or "").strip()
        if user_id.isdigit():
            qs = qs.filter(user_id=int(user_id))

        from_dt = self.request.query_params.get("from")
        to_dt = self.request.query_params.get("to")
        if from_dt:
            try:
                qs = qs.filter(requested_at__gte=from_dt)
            except Exception:
                pass
        if to_dt:
            try:
                qs = qs.filter(requested_at__lte=to_dt)
            except Exception:
                pass

        return qs


class AdminWithdrawalDetailView(BaseAppAdminAPIView, RetrieveAPIView):
    """GET /api/admin/withdrawals/<withdrawal_id>/"""
    queryset = Withdrawal.objects.select_related("user", "ledger_entry")
    serializer_class = AdminWithdrawalSerializer
    lookup_url_kwarg = "withdrawal_id"


class AdminWithdrawalRetryView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """POST /api/admin/withdrawals/<withdrawal_id>/retry/"""
    allowed_roles = {
        AppAdmin.Role.FINANCE,
        AppAdmin.Role.SUPERVISOR,
        AppAdmin.Role.ADMIN,
        AppAdmin.Role.OWNER,
    }

    def post(self, request, withdrawal_id):
        self._require_app_admin_roles(request, self.allowed_roles)

        withdrawal = Withdrawal.objects.filter(id=withdrawal_id).first()
        if not withdrawal:
            raise NotFound("Withdrawal not found")

        execute_realtime_withdrawal.delay(str(withdrawal.id))
        return Response(
            {"detail": "Withdrawal retry queued", "withdrawal_id": str(withdrawal.id)}
        )


class AdminWithdrawalMarkPaidView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """POST /api/admin/withdrawals/<withdrawal_id>/mark-paid/"""
    allowed_roles = {
        AppAdmin.Role.FINANCE,
        AppAdmin.Role.SUPERVISOR,
        AppAdmin.Role.ADMIN,
        AppAdmin.Role.OWNER,
    }

    def post(self, request, withdrawal_id):
        self._require_app_admin_roles(request, self.allowed_roles)

        withdrawal = (
            Withdrawal.objects.filter(id=withdrawal_id).select_related("user").first()
        )
        if not withdrawal:
            raise NotFound("Withdrawal not found")

        mark_withdrawal_paid(withdrawal)
        return Response(
            {
                "detail": "Withdrawal marked as complete",
                "withdrawal_id": str(withdrawal.id),
                "status": withdrawal.status,
            }
        )


class AdminWithdrawalMarkFailedView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """POST /api/admin/withdrawals/<withdrawal_id>/mark-failed/"""
    allowed_roles = {
        AppAdmin.Role.FINANCE,
        AppAdmin.Role.SUPERVISOR,
        AppAdmin.Role.ADMIN,
        AppAdmin.Role.OWNER,
    }
    serializer_class = AdminWithdrawalMarkFailedSerializer

    def post(self, request, withdrawal_id):
        self._require_app_admin_roles(request, self.allowed_roles)

        withdrawal = (
            Withdrawal.objects.filter(id=withdrawal_id)
            .select_related("user", "ledger_entry")
            .first()
        )
        if not withdrawal:
            raise NotFound("Withdrawal not found")

        vd = self.validate_serializer(request.data)
        mark_withdrawal_failed(withdrawal, vd["reason"])
        return Response(
            {
                "detail": "Withdrawal marked as failed",
                "withdrawal_id": str(withdrawal.id),
                "status": withdrawal.status,
            }
        )


class AdminWithdrawalBatchExecuteView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """POST /api/admin/withdrawals/batch/execute/"""
    allowed_roles = {AppAdmin.Role.FINANCE, AppAdmin.Role.ADMIN, AppAdmin.Role.OWNER}

    def post(self, request):
        self._require_app_admin_roles(request, self.allowed_roles)
        execute_batch_payouts.delay()
        return Response({"detail": "Batch payouts execution queued"})


class AdminWithdrawalReconcileView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """POST /api/admin/withdrawals/reconcile/"""
    allowed_roles = {AppAdmin.Role.FINANCE, AppAdmin.Role.ADMIN, AppAdmin.Role.OWNER}

    def post(self, request):
        self._require_app_admin_roles(request, self.allowed_roles)
        reconcile_stale_processing_withdrawals.delay()
        retry_pending_withdrawals.delay()
        return Response({"detail": "Reconciliation + retry queued"})


class AdminReferralPayoutListView(BaseAppAdminAPIView, ListAPIView):
    """GET /api/admin/referrals/payouts/"""
    serializer_class = ReferralPayoutSerializer

    def get_queryset(self):
        qs = ReferralPayout.objects.select_related("user").order_by("-created_at")
        user_id = self.request.query_params.get("user_id")
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        total_units = qs.aggregate(total=Sum("units_paid"))["total"] or 0

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data["total_units_paid"] = total_units
            return response

        serializer = self.get_serializer(qs, many=True)
        return Response(
            {
                "results": serializer.data,
                "total_units_paid": total_units,
            }
        )


class AdminReferralPayoutDetailView(BaseAppAdminAPIView, RetrieveAPIView):
    """GET /api/admin/referrals/payouts/<pk>/"""
    queryset = ReferralPayout.objects.all()
    serializer_class = ReferralPayoutSerializer

    def retrieve(self, request, *args, **kwargs):
        payout = self.get_object()
        return Response(
            {
                "id": payout.id,
                "user_id": payout.user_id,
                "units_paid": payout.units_paid,
                "referrals_used": payout.referrals_used,
                "created_at": payout.created_at,
                "referrals": payout.referral_snapshot,
                "is_valid": verify_snapshot_integrity(payout),
            }
        )
