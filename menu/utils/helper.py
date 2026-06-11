from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.db.models import (
    OuterRef, Subquery, Prefetch, Q, Count,
    F, FloatField, ExpressionWrapper
)
from accounts.models import BranchOperatingHours, Branch
from django.utils import timezone
from datetime import timedelta

# ============================================================================
# SHARED HELPERS
# ============================================================================

def nearest_branch_subquery(user_point, max_km=15):
    return (
        Branch.objects
        .filter(
            business_id=OuterRef("pk"),
            is_active=True,
            is_accepting_orders=True,
            location__isnull=False,
            location__distance_lte=(user_point, D(km=max_km)),
        )
        .annotate(dist=Distance("location", user_point))
        .order_by("dist")
    )


def annotate_with_nearest_branch(qs, user_point, max_km=15):
    branch_qs = nearest_branch_subquery(user_point, max_km)

    return qs.annotate(
        nearest_branch_id=Subquery(branch_qs.values("id")[:1]),
        nearest_branch_distance=Subquery(branch_qs.values("dist")[:1]),
    )


# def bulk_load_branches(businesses):
#     branch_ids = [
#         b.nearest_branch_id for b in businesses
#         if getattr(b, "nearest_branch_id", None)
#     ]

#     if not branch_ids:
#         return {}

#     return {
#         b.id: b
#         for b in Branch.objects.filter(id__in=branch_ids)
#     }


def bulk_load_branches(businesses):
    branch_ids = [
        b.nearest_branch_id for b in businesses
        if getattr(b, "nearest_branch_id", None)
    ]
    if not branch_ids:
        return {}

    today = timezone.localtime().weekday()

    return {
        b.id: b
        for b in Branch.objects
            .filter(id__in=branch_ids)
            .prefetch_related(
                Prefetch(
                    "operating_hours",
                    queryset=BranchOperatingHours.objects.filter(day=today),
                    to_attr="todays_hours"  # branch.todays_hours -> list
                )
            )
    }


def annotate_business_metrics(qs, user_point):
    branch_qs = nearest_branch_subquery(user_point)

    return qs.annotate(
        # nearest branch
        nearest_branch_id=Subquery(branch_qs.values("id")[:1]),
        nearest_branch_distance=Subquery(branch_qs.values("dist")[:1]),

        # rating signal
        # avg_rating=Avg("branches__ratings__value"), # was conflicting and was removed

        # demand signal (orders in last 30 days)
        order_count_30d=Count(
            "branches__orders",
            filter=Q(branches__orders__created_at__gte=timezone.now() - timedelta(days=30))
        ),

        # # lifetime popularity (smoothed)
        # total_orders=Count("branches__orders"),
    )


def apply_top_picks_ranking(qs):
    return qs.annotate(
        top_pick_score=ExpressionWrapper(
            (F("avg_rating") * 0.4) +
            (F("order_count_30d") * 0.4) +
            #(F("total_orders") * 0.1) -
            - (F("nearest_branch_distance") * 0.1),
            output_field=FloatField()
        )
    )


def is_branch_open(branch) -> bool:
    now = timezone.localtime()

    # Use prefetched todays_hours if available, else fall back to DB query
    if hasattr(branch, "todays_hours"):
        hours_list = branch.todays_hours  # already filtered to today
        if not hours_list:
            return True
        hours = hours_list[0]
    else:
        try:
            hours = branch.operating_hours.get(day=now.weekday())
        except BranchOperatingHours.DoesNotExist:
            return True

    if hours.is_closed:
        return False

    return hours.open_time <= now.time() <= hours.close_time
