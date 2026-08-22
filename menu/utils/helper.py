from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.db.models import (
    OuterRef, Subquery, Prefetch, Q, Count,
    F, FloatField, ExpressionWrapper, Case, When, Value, Exists
)
from accounts.models import BranchOperatingHours, Branch, Business
from payments.models.subscription import Subscription
from django.utils import timezone
from datetime import timedelta
from authflow.features import TOP3_FEATURE_CODE, HIGH_RANK_FEATURE_CODE, HIGH_RANK_BOOST
import hashlib
from datetime import date
from collections import defaultdict
from menu.models import MenuItem

MENU_MATCH_LIMIT = 3

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
            (F("avg_rating") * 0.4)
            + (F("order_count_30d") * 0.4)
            - (F("nearest_branch_distance") * 0.1)
            + Case(
                When(has_high_rank=True, then=Value(HIGH_RANK_BOOST)),
                default=Value(0),
                output_field=FloatField(),
            ),
            output_field=FloatField(),
        )
    )


def get_hours(branch) -> BranchOperatingHours:
    # Use prefetched todays_hours if available, else fall back to DB query
    now = timezone.localtime()

    if hasattr(branch, "todays_hours"):
        hours_list = branch.todays_hours  # already filtered to today
        if not hours_list:
            return None
        hours = hours_list[0]
    else:
        try:
            hours = branch.operating_hours.get(day=now.weekday())
        except BranchOperatingHours.DoesNotExist:
            return None

    return hours


def is_branch_open(branch) -> bool:
    now = timezone.localtime()

    hours = get_hours(branch)
    if not hours:
        return True

    if hours.is_closed:
        return False

    return hours.open_time <= now.time() <= hours.close_time


def is_branch_hours_open(hours: BranchOperatingHours) -> bool:
    now = timezone.localtime()
    if not hours:
        return True

    if hours.is_closed:
        return False

    return hours.open_time <= now.time() <= hours.close_time


def _active_subscription_feature_subquery(feature_code):
    """
    Exists subquery: does the business's owning user have an active
    subscription on a plan carrying `feature_code`?
    """
    return Exists(
        Subscription.objects.filter(
            user_id=OuterRef("admin__user_id"),  # <-- adjust to your real owner field
            active=True,
            plan__features__code=feature_code,
        )
    )


def annotate_subscription_tiers(qs):
    return qs.annotate(
        has_top3=_active_subscription_feature_subquery(TOP3_FEATURE_CODE),
        has_high_rank=_active_subscription_feature_subquery(HIGH_RANK_FEATURE_CODE),
    )


class DailyRotationMixin:
    """Mixin to provide deterministic daily random ordering."""
    
    def get_daily_seed(self) -> float:
        """
        Generates a stable float between 0.0 and 1.0 based on today's date.
        This provides a consistent seed for databases that require it.
        """
        today_str = str(date.today())
        # Hash the date string to get a deterministic integer, then convert to a float 0.0-1.0
        hash_val = int(hashlib.md5(today_str.encode("utf-8")).hexdigest(), 16)
        return (hash_val % 10000) / 10000.0

    def apply_daily_rotation(self, queryset):
        """
        Applies a repeatable daily shuffle across different databases.
        For PostgreSQL/MySQL, we set a seed session variable before ordering by random().
        """
        # If using PostgreSQL:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT setseed({self.get_daily_seed()});")
            
        # Order by random() - because setseed() was called, this order is fixed for the day
        return queryset.order_by("?")

def in_stock_menu_item_exists(query):
    """
    Exists(...) condition for a Business queryset that already has
    `nearest_branch_id` annotated (see annotate_with_nearest_branch).
    Combine with other Q() conditions using `|` / `&` as normal.

    True when the business has at least one menu item whose name
    matches `query` and is in stock (no explicit is_available=False
    row) at the business's nearest branch. No row => in stock.
    """
    return Exists(
        MenuItem.objects.filter(
            category__menu__business_id=OuterRef("pk"),
            custom_name__icontains=query,
        ).exclude(
            base_item__item_availabilities__branch_id=OuterRef("nearest_branch_id"),
            base_item__item_availabilities__is_available=False,
        )
    )


def get_menu_matches_for_businesses(businesses, query, user_point, max_km=15, limit=MENU_MATCH_LIMIT):
    """
    Return in-stock menu-item search matches grouped by business.

    An item only counts as a match if it's in stock at the business's
    nearest branch -- the same rule that decides whether the business
    matched the search at all (see in_stock_menu_item_exists), so
    total_matches here is always real: total_matches == 0 for a given
    business can't happen for a business that reached this function via
    a menu-item match.

    Result:

    {
        business_id: {
            "matches": [
                {"id": 123, "name": "Cheese Burger"},
                {"id": 124, "name": "Ham Burger"},
            ],
            "total_matches": 15,   # total valid (in-stock) matches
        }
    }

    Only the first `limit` matches are returned per business.
    """
    business_ids = [business.id for business in businesses]

    if not business_ids or not query:
        return {}

    nearest_branch_for_item = (
        Branch.objects
        .filter(
            business_id=OuterRef("category__menu__business_id"),
            is_active=True,
            is_accepting_orders=True,
            location__isnull=False,
            location__distance_lte=(user_point, D(km=max_km)),
        )
        .annotate(dist=Distance("location", user_point))
        .order_by("dist")
        .values("id")[:1]
    )

    rows = (
        MenuItem.objects
        .filter(
            category__menu__business_id__in=business_ids,
            custom_name__icontains=query,
        )
        .annotate(nearest_branch_id=Subquery(nearest_branch_for_item))
        .exclude(
            base_item__item_availabilities__branch_id=F("nearest_branch_id"),
            base_item__item_availabilities__is_available=False,
        )
        .values(
            "category__menu__business_id",
            "id",
            "custom_name",
        )
        .order_by("category__menu__business_id", "id")
    )

    grouped = defaultdict(lambda: {"matches": [], "total_matches": 0})

    for row in rows:
        business_id = row["category__menu__business_id"]

        grouped[business_id]["total_matches"] += 1

        if len(grouped[business_id]["matches"]) < limit:
            grouped[business_id]["matches"].append({
                "id": row["id"],
                "name": row["custom_name"],
            })

    return dict(grouped)
