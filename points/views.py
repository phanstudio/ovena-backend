"""
payments/points/views.py

Generic API views only -- no business logic here, everything routes through
payments.points.service. Endpoints:

  GET    /points/balances/              admin: every user + their points balance
  GET    /points/me/balance/            self: current user's balance
  GET    /points/me/history/            self: ledger feed (what earned these points)
  GET    /points/me/withdrawals/        self: my withdrawal request history
  POST   /points/withdrawals/           self: request a withdrawal
  GET    /points/withdrawals/admin/     admin: all withdrawal requests (filter by ?status=)
  PATCH  /points/withdrawals/<id>/resolve/   admin: approve/reject/mark paid
  GET/POST   /points/rules/             admin: list/create point-value rules
  GET/PATCH  /points/rules/<id>/        admin: view/update a rule
"""

from django.contrib.auth import get_user_model
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from points import leaderboard_service, service
from points.models import PointsEventRule, PointsLedgerEntry, PointsWithdrawalRequest
from points.serializers import (
    LeaderboardEntrySerializer,
    LeaderboardPeriodSerializer,
    MyLeaderboardRankSerializer,
    PointsBalanceSerializer,
    PointsEventRuleSerializer,
    PointsLedgerEntrySerializer,
    PointsWithdrawalRequestCreateSerializer,
    PointsWithdrawalRequestSerializer,
    PointsWithdrawalResolveSerializer,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Balances -- "list of individuals and their points"
# ---------------------------------------------------------------------------

class PointsBalanceListView(generics.ListAPIView):
    """Admin/ops view: every user with a points balance, highest first."""

    serializer_class = PointsBalanceSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return (
            User.objects.annotate(
                points_balance=Coalesce(Sum("points_entries__points"), Value(0))
            )
            .exclude(points_balance=0)
            .order_by("-points_balance")
            .values("id", "name", "points_balance")
        )

    def list(self, request, *args, **kwargs):
        rows = list(self.get_queryset())
        data = [
            {"user_id": str(r["id"]), "name": r["name"] or "", "points_balance": r["points_balance"]}
            for r in rows
        ]
        page = self.paginate_queryset(data)
        serializer = self.get_serializer(page if page is not None else data, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class MyPointsBalanceView(generics.RetrieveAPIView):
    """Current user's own balance, for a profile/rewards screen."""

    serializer_class = PointsBalanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        user = self.request.user
        return {
            "user_id": str(user.id),
            "name": getattr(user, "name", "") or "",
            "points_balance": service.get_points_balance(user),
        }


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class MyPointsHistoryListView(generics.ListAPIView):
    """Current user's ledger feed -- what earned/spent each point."""

    serializer_class = PointsLedgerEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PointsLedgerEntry.objects.filter(user=self.request.user).order_by("-created_at")


# ---------------------------------------------------------------------------
# Withdrawals
# ---------------------------------------------------------------------------

class PointsWithdrawalRequestCreateView(generics.CreateAPIView):
    """POST to request a redemption of points."""

    serializer_class = PointsWithdrawalRequestCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            withdrawal = service.create_points_withdrawal_request(
                user=request.user,
                points_requested=serializer.validated_data["points_requested"],
                idempotency_key=serializer.validated_data["idempotency_key"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        out = PointsWithdrawalRequestSerializer(withdrawal)
        return Response(out.data, status=status.HTTP_201_CREATED)


class MyPointsWithdrawalRequestListView(generics.ListAPIView):
    """Current user's own withdrawal request history."""

    serializer_class = PointsWithdrawalRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PointsWithdrawalRequest.objects.filter(user=self.request.user).order_by("-requested_at")


class PointsWithdrawalRequestAdminListView(generics.ListAPIView):
    """Admin/ops: every withdrawal request, optionally filtered by status."""

    serializer_class = PointsWithdrawalRequestSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        qs = PointsWithdrawalRequest.objects.select_related("user").order_by("-requested_at")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class PointsWithdrawalRequestResolveView(generics.GenericAPIView):
    """PATCH to approve/reject/mark-paid a withdrawal request."""

    serializer_class = PointsWithdrawalResolveSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = PointsWithdrawalRequest.objects.all()

    def patch(self, request, *args, **kwargs):
        instance = self.get_object()

        # Once money has actually moved (paid), this record is terminal.
        # Any correction from here on is a refund/chargeback against the
        # real money ledger, not a points-side reversal -- so we don't let
        # this endpoint touch a paid request at all.
        if instance.status == "paid":
            return Response(
                {"detail": "This request has already been paid and can't be modified here. "
                           "Corrections after payout go through the payments ledger, not the points ledger."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]

        instance.status = new_status
        instance.resolved_at = timezone.now()
        instance.save(update_fields=["status", "resolved_at"])

        # A rejection releases the held points back to the user's balance.
        # This is safe precisely because no money was disbursed yet -- it's
        # purely undoing a hold on a number that was never real currency.
        if new_status == "rejected" and instance.ledger_entry_id:
            service.reverse_points_award(
                instance.ledger_entry, reason="Withdrawal request rejected"
            )

        return Response(PointsWithdrawalRequestSerializer(instance).data)


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

class LeaderboardCurrentView(generics.ListAPIView):
    """
    Current month's live standings. Computed from the ledger and briefly
    cached (see leaderboard_service) -- resets to empty on its own on the
    1st of each month since it's just a date-filtered query.
    """

    serializer_class = LeaderboardEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None  # this is a top-N board, not a paged table

    def list(self, request, *args, **kwargs):
        limit = int(request.query_params.get("limit", 50))
        data = leaderboard_service.get_live_leaderboard(limit=limit)
        return Response(self.get_serializer(data, many=True).data)


class MyLeaderboardRankView(generics.GenericAPIView):
    """Current user's own rank + points for the current (unfinished) month."""

    serializer_class = MyLeaderboardRankSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        data = leaderboard_service.get_my_live_rank(request.user)
        return Response(self.get_serializer(data).data)


class LeaderboardSnapshotPeriodListView(generics.GenericAPIView):
    """Which past months have a finalized leaderboard available."""

    serializer_class = LeaderboardPeriodSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        periods = leaderboard_service.list_snapshot_periods()
        data = [{"period": p} for p in periods]
        return Response(self.get_serializer(data, many=True).data)


class LeaderboardSnapshotView(generics.ListAPIView):
    """
    A past month's frozen standings, e.g. GET /points/leaderboard/2026-06/.
    404s if that month was never finalized (still current, or too old /
    never ran).
    """

    serializer_class = LeaderboardEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def list(self, request, *args, **kwargs):
        from datetime import date as _date

        period_str = self.kwargs["period"]  # "YYYY-MM"
        try:
            year, month = (int(p) for p in period_str.split("-"))
            period = _date(year, month, 1)
        except (ValueError, IndexError):
            return Response({"detail": "period must be formatted YYYY-MM"}, status=status.HTTP_400_BAD_REQUEST)

        limit = int(request.query_params.get("limit", 50))
        data = leaderboard_service.get_snapshot_leaderboard(period, limit=limit)
        if not data and period not in leaderboard_service.list_snapshot_periods():
            return Response({"detail": "No finalized leaderboard for that period."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(data, many=True).data)


# ---------------------------------------------------------------------------
# Event rules -- the "more rules coming" lever
# ---------------------------------------------------------------------------

class PointsEventRuleListView(generics.ListCreateAPIView):
    """Admin: list existing point-value rules / add a new event type."""

    serializer_class = PointsEventRuleSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = PointsEventRule.objects.all().order_by("event_type")


class PointsEventRuleDetailView(generics.RetrieveUpdateAPIView):
    """Admin: view or adjust a single rule's value/active state."""

    serializer_class = PointsEventRuleSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = PointsEventRule.objects.all()
