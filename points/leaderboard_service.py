from __future__ import annotations

"""
payments/points/leaderboard_service.py

Public API:
  - get_live_leaderboard(limit=50)             current month, computed from
                                                the ledger, short-TTL cached
  - get_my_live_rank(user)                     current user's rank + points
                                                this month (uncached, single row)
  - finalize_leaderboard_for_period(period)     freeze last month's standings
                                                into MonthlyLeaderboardSnapshot
  - get_snapshot_leaderboard(period)            fetch a past month's frozen
                                                standings
  - list_snapshot_periods()                     which past months have a
                                                finalized snapshot

"period" is always a date on the 1st of the month, e.g. date(2026, 7, 1).
"""

import calendar
import logging
from datetime import date

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from points.models import (
    MonthlyLeaderboardEntry,
    MonthlyLeaderboardSnapshot,
    PointsLedgerEntry,
)

logger = logging.getLogger(__name__)

User = get_user_model()

LIVE_LEADERBOARD_CACHE_TTL_SECONDS = 90
LIVE_LEADERBOARD_CACHE_KEY = "points:leaderboard:live:{period}:{limit}"


def _month_bounds(period: date) -> tuple[date, date]:
    period_start = period.replace(day=1)
    last_day = calendar.monthrange(period_start.year, period_start.month)[1]
    period_end = period_start.replace(day=last_day)
    return period_start, period_end


def current_period() -> date:
    return timezone.now().date().replace(day=1)


def previous_period(period: date | None = None) -> date:
    """The month before `period` (defaults to now) -- what finalize normally targets."""
    ref = (period or current_period()).replace(day=1)
    return (ref.replace(day=1) - timezone.timedelta(days=1)).replace(day=1)


# ---------------------------------------------------------------------------
# Live (current month) -- always computed from the ledger, briefly cached
# ---------------------------------------------------------------------------

def get_live_leaderboard(limit: int = 50, use_cache: bool = True) -> list[dict]:
    """
    Current month's standings. This never persists anything -- it's a
    point-in-time read of the ledger for [period_start, now]. Cached for a
    short TTL so a busy leaderboard screen doesn't re-run the aggregate on
    every request; the cache just holds this query's result, it is not a
    separate source of truth.
    """
    period = current_period()
    cache_key = LIVE_LEADERBOARD_CACHE_KEY.format(period=period.isoformat(), limit=limit)

    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    period_start, period_end = _month_bounds(period)
    rows = (
        User.objects.filter(
            points_entries__created_at__date__gte=period_start,
            points_entries__created_at__date__lte=period_end,
        )
        .annotate(points_this_month=Coalesce(Sum("points_entries__points"), Value(0)))
        .exclude(points_this_month__lte=0)
        .order_by("-points_this_month")[:limit]
        .values("id", "name", "points_this_month")
    )

    results = [
        {"rank": idx + 1, "user_id": str(r["id"]), "name": r["name"] or "", "points": r["points_this_month"]}
        for idx, r in enumerate(rows)
    ]

    if use_cache:
        cache.set(cache_key, results, LIVE_LEADERBOARD_CACHE_TTL_SECONDS)
    return results


def get_my_live_rank(user) -> dict:
    """
    Uncached on purpose: this is a single user's row, not the whole ranked
    list, so it's cheap, and it should always reflect their latest action
    (e.g. right after they rate an order) rather than a stale cache hit.
    """
    period_start, period_end = _month_bounds(current_period())
    points = (
        PointsLedgerEntry.objects.filter(
            user=user, created_at__date__gte=period_start, created_at__date__lte=period_end
        ).aggregate(total=Sum("points"))["total"]
        or 0
    )
    rank = (
        User.objects.filter(
            points_entries__created_at__date__gte=period_start,
            points_entries__created_at__date__lte=period_end,
        )
        .annotate(points_this_month=Coalesce(Sum("points_entries__points"), Value(0)))
        .filter(points_this_month__gt=points)
        .count()
        + 1
    )
    return {"user_id": str(user.id), "points": points, "rank": rank if points > 0 else None}


# ---------------------------------------------------------------------------
# Finalize -- run once, right after a month ends (cron/celery-beat on the 1st)
# ---------------------------------------------------------------------------

@transaction.atomic
def finalize_leaderboard_for_period(period: date | None = None) -> MonthlyLeaderboardSnapshot:
    """
    Freezes the standings for `period` (defaults to last month). Idempotent:
    calling it twice for the same period returns the existing snapshot
    rather than creating a duplicate or recomputing.
    """
    target_period = (period or previous_period()).replace(day=1)
    period_start, period_end = _month_bounds(target_period)

    existing = MonthlyLeaderboardSnapshot.objects.filter(period_start=period_start).first()
    if existing:
        logger.info("points.leaderboard.finalize.already_exists", extra={"period": str(period_start)})
        return existing

    rows = (
        User.objects.filter(
            points_entries__created_at__date__gte=period_start,
            points_entries__created_at__date__lte=period_end,
        )
        .annotate(points_total=Coalesce(Sum("points_entries__points"), Value(0)))
        .exclude(points_total__lte=0)
        .order_by("-points_total")
        .values("id", "points_total")
    )

    snapshot = MonthlyLeaderboardSnapshot.objects.create(
        period_start=period_start, period_end=period_end
    )
    MonthlyLeaderboardEntry.objects.bulk_create(
        [
            MonthlyLeaderboardEntry(
                snapshot=snapshot, user_id=row["id"], points=row["points_total"], rank=idx + 1
            )
            for idx, row in enumerate(rows)
        ]
    )

    logger.info(
        "points.leaderboard.finalized",
        extra={"period": str(period_start), "entry_count": len(rows)},
    )
    return snapshot


# ---------------------------------------------------------------------------
# Read a past, finalized month
# ---------------------------------------------------------------------------

def get_snapshot_leaderboard(period: date, limit: int = 50) -> list[dict]:
    period_start = period.replace(day=1)
    entries = (
        MonthlyLeaderboardEntry.objects.filter(snapshot__period_start=period_start)
        .select_related("user")
        .order_by("rank")[:limit]
    )
    return [
        {"rank": e.rank, "user_id": str(e.user_id), "name": getattr(e.user, "name", "") or "", "points": e.points}
        for e in entries
    ]


def list_snapshot_periods() -> list[date]:
    return list(
        MonthlyLeaderboardSnapshot.objects.order_by("-period_start").values_list("period_start", flat=True)
    )
