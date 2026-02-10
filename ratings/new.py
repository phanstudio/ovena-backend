from django.test import TestCase

# Create your tests here.



from django.conf import settings
from django.db.models import Avg, Count, Value, FloatField
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D

def find_nearest_available_drivers(branch_location, max_drivers=3):
    stale_threshold = timezone.now() - timezone.timedelta(
        seconds=settings.DRIVER_LOCATION_STALE_THRESHOLD
    )

    # Tuning knobs (put these in settings ideally)
    CANDIDATE_MULTIPLIER = getattr(settings, "DRIVER_CANDIDATE_MULTIPLIER", 5)  # fetch more than max_drivers
    DISTANCE_TOLERANCE_KM = getattr(settings, "DRIVER_DISTANCE_TOLERANCE_KM", 0.7)  # "small amount"
    MIN_RATING_COUNT = getattr(settings, "DRIVER_MIN_RATING_COUNT", 5)  # don't trust 1 rating

    search_radiuses = settings.DRIVER_SEARCH_RADIUS_KM  # [5, 10, 15]

    def build_queryset(radius_km=None):
        qs = DriverLocation.objects.filter(
            is_online=True,
            last_updated__gte=stale_threshold,
            driver__is_available=True,
            driver__current_order__isnull=True,
        ).select_related("driver", "driver__user").annotate(
            distance=Distance("location", branch_location),
            # avg/count from DriverRating related_name="ratings_received"
            rating_avg=Coalesce(Avg("driver__ratings_received__stars"), Value(0.0)),
            rating_count=Coalesce(Count("driver__ratings_received__id"), Value(0)),
        )

        if radius_km is not None:
            qs = qs.filter(location__distance_lte=(branch_location, D(km=radius_km)))
        return qs

    for radius in search_radiuses:
        candidates = list(
            build_queryset(radius_km=radius)
            .order_by("distance")[: max_drivers * CANDIDATE_MULTIPLIER]
        )
        if candidates:
            return _rank_driver_candidates(
                candidates,
                max_drivers=max_drivers,
                distance_tolerance_km=DISTANCE_TOLERANCE_KM,
                min_rating_count=MIN_RATING_COUNT,
            )

    # fallback: nearest overall
    candidates = list(
        build_queryset(radius_km=None)
        .order_by("distance")[: max_drivers * CANDIDATE_MULTIPLIER]
    )
    if candidates:
        return _rank_driver_candidates(
            candidates,
            max_drivers=max_drivers,
            distance_tolerance_km=DISTANCE_TOLERANCE_KM,
            min_rating_count=MIN_RATING_COUNT,
        )

    return []


def _rank_driver_candidates(candidates, max_drivers, distance_tolerance_km, min_rating_count):
    """
    candidates: list of DriverLocation objects annotated with distance, rating_avg, rating_count.
    Returns list of (driver_profile, distance_km).
    """
    # smallest distance
    closest_km = candidates[0].distance.km

    # Only allow rating to influence inside a tight window.
    window = [
        c for c in candidates
        if c.distance.km <= closest_km + distance_tolerance_km
    ]

    # If window is too small (e.g. only 1), expand to at least max_drivers by distance
    if len(window) < max_drivers:
        window = candidates[:max_drivers]

    def score(c):
        # Base: prefer distance strongly
        dist_penalty = c.distance.km

        # Rating bonus: only if enough ratings; scale is small
        if c.rating_count >= min_rating_count:
            # convert 1..5 into a small negative penalty (better rating => smaller score)
            rating_bonus = (5.0 - float(c.rating_avg)) * 0.10  # 0..0.4 km-equivalent penalty
        else:
            rating_bonus = 0.0

        return dist_penalty + rating_bonus

    window.sort(key=score)

    return [(c.driver, c.distance.km) for c in window[:max_drivers]]





from django.conf import settings
from django.utils import timezone
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D


def find_nearest_available_drivers(branch_location, max_drivers=3):
    stale_threshold = timezone.now() - timezone.timedelta(
        seconds=settings.DRIVER_LOCATION_STALE_THRESHOLD
    )

    # tuning knobs
    CANDIDATE_MULTIPLIER = getattr(settings, "DRIVER_CANDIDATE_MULTIPLIER", 5)
    DISTANCE_TOLERANCE_KM = getattr(settings, "DRIVER_DISTANCE_TOLERANCE_KM", 0.7)
    MIN_RATING_COUNT = getattr(settings, "DRIVER_MIN_RATING_COUNT", 5)

    search_radiuses = settings.DRIVER_SEARCH_RADIUS_KM  # [5, 10, 15]

    def base_qs(radius_km=None):
        qs = DriverLocation.objects.filter(
            is_online=True,
            last_updated__gte=stale_threshold,
            driver__is_available=True,
            driver__current_order__isnull=True,
        ).select_related("driver", "driver__user").annotate(
            distance=Distance("location", branch_location)
        )
        if radius_km is not None:
            qs = qs.filter(location__distance_lte=(branch_location, D(km=radius_km)))
        return qs

    for radius in search_radiuses:
        candidates = list(
            base_qs(radius_km=radius)
            .order_by("distance")[: max_drivers * CANDIDATE_MULTIPLIER]
        )
        if candidates:
            return _rank_candidates_fast(
                candidates,
                max_drivers=max_drivers,
                distance_tolerance_km=DISTANCE_TOLERANCE_KM,
                min_rating_count=MIN_RATING_COUNT,
            )

    # fallback overall
    candidates = list(
        base_qs(radius_km=None).order_by("distance")[: max_drivers * CANDIDATE_MULTIPLIER]
    )
    if candidates:
        return _rank_candidates_fast(
            candidates,
            max_drivers=max_drivers,
            distance_tolerance_km=DISTANCE_TOLERANCE_KM,
            min_rating_count=MIN_RATING_COUNT,
        )

    return []


def _rank_candidates_fast(candidates, max_drivers, distance_tolerance_km, min_rating_count):
    closest_km = candidates[0].distance.km

    # only allow rating preference inside a tight distance window
    window = [c for c in candidates if c.distance.km <= closest_km + distance_tolerance_km]
    if len(window) < max_drivers:
        window = candidates[:max_drivers]

    def score(c):
        d_km = c.distance.km
        driver = c.driver

        # strongly prefer distance
        score_val = d_km

        # small rating bias if trusted
        if (driver.rating_count or 0) >= min_rating_count:
            # Better rating => smaller score (small influence)
            # 5.0 -> +0, 4.0 -> +0.10, 3.0 -> +0.20 etc (tune)
            score_val += (5.0 - float(driver.avg_rating or 0.0)) * 0.10

        return score_val

    window.sort(key=score)
    return [(c.driver, c.distance.km) for c in window[:max_drivers]]


# Branch.objects.order_by("-avg_rating", "-rating_count")