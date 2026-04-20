from __future__ import annotations

from typing import Optional

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet


PROFILE_CUSTOMER = "customer"
PROFILE_DRIVER = "driver"
PROFILE_BUSINESS_ADMIN = "businessadmin"
PROFILE_BUSINESS_STAFF = "businessstaff"
PROFILE_APP_ADMIN = "appadmin"

_LEGACY_ALIASES = {
    "buisnessstaff": PROFILE_BUSINESS_STAFF,
    "restaurantstaff": PROFILE_BUSINESS_STAFF,
}

PROFILE_PREFETCHES = {
    PROFILE_CUSTOMER: {
        "prefetch": ["profile_bases__customer_profile"],
    },
    PROFILE_DRIVER: {
        "prefetch": ["profile_bases__driver_profile"],
    },
    PROFILE_BUSINESS_ADMIN: {
        "select": ["business_admin"],
    },
    PROFILE_BUSINESS_STAFF: {
        "select": ["primary_agent", "primary_agent__branch"],
    },
    PROFILE_APP_ADMIN: {
        "select": ["app_admin"],
    },
}


def normalize_profile_type(profile_type: Optional[str]) -> Optional[str]:
    if not profile_type:
        return None
    pt = profile_type.strip().lower()
    return _LEGACY_ALIASES.get(pt, pt)


# def get_profile(user, profile_type: str):
#     """
#     Generic profile resolver used by auth + permissions.
#     Works with the current base_profile linkage and remains stable for MTI cutover.
#     """
#     from accounts.models import ProfileBase

#     pt = normalize_profile_type(profile_type)
#     if not user or not getattr(user, "is_authenticated", False) or not pt:
#         return None

#     if pt == PROFILE_CUSTOMER:
#         base = (
#             ProfileBase.objects.filter(user=user, profile_type=PROFILE_CUSTOMER)
#             .select_related("customer_profile")
#             .first()
#         )
#         return getattr(base, "customer_profile", None) if base else None

#     if pt == PROFILE_DRIVER:
#         base = (
#             ProfileBase.objects.filter(user=user, profile_type=PROFILE_DRIVER)
#             .select_related("driver_profile")
#             .first()
#         )
#         return getattr(base, "driver_profile", None) if base else None

#     if pt == PROFILE_BUSINESS_ADMIN:
#         try:
#             return user.business_admin
#         except ObjectDoesNotExist:
#             return None

#     if pt == PROFILE_BUSINESS_STAFF:
#         try:
#             return user.primary_agent
#         except ObjectDoesNotExist:
#             return None

#     return None


def has_profile(user, profile_type: str) -> bool:
    return get_profile(user, profile_type) is not None


def resolve_active_profile_type(
    *, request, user, allowed_types: list[str]
) -> Optional[str]:
    """
    Resolve profile context for a request:
    1. X-Profile-Type header
    2. token claim 'active_profile'
    3. first allowed type user actually has
    """
    normalized_allowed = [normalize_profile_type(t) for t in allowed_types]
    normalized_allowed = [t for t in normalized_allowed if t]

    header_type = normalize_profile_type(request.headers.get("X-Profile-Type"))
    if (
        header_type
        and header_type in normalized_allowed
        and has_profile(user, header_type)
    ):
        return header_type

    auth = getattr(request, "_auth", None)
    token_type = None
    if auth is not None:
        try:
            token_type = normalize_profile_type(auth.get("active_profile"))
        except Exception:
            token_type = None
    if (
        token_type
        and token_type in normalized_allowed
        and has_profile(user, token_type)
    ):
        return token_type

    for profile_type in normalized_allowed:
        if has_profile(user, profile_type):
            return profile_type

    return None


def apply_profile_fetches(
    queryset: QuerySet, profile_types: list[str] | None = None
) -> QuerySet:
    """
    Apply the correct select_related/prefetch_related for given profile types.
    Pass None to load all profiles.

    Usage:
        qs = apply_profile_fetches(User.objects.filter(...), [PROFILE_CUSTOMER, PROFILE_DRIVER])
        qs = apply_profile_fetches(User.objects.filter(...))  # loads everything
    """
    types = profile_types or list(PROFILE_PREFETCHES.keys())

    selects = []
    prefetches = []

    for pt in types:
        normalized = normalize_profile_type(pt)
        config = PROFILE_PREFETCHES.get(normalized)
        if not config:
            continue
        selects.extend(config.get("select", []))
        prefetches.extend(config.get("prefetch", []))

    if selects:
        queryset = queryset.select_related(*selects)
    if prefetches:
        queryset = queryset.prefetch_related(*prefetches)

    return queryset


def _profile_cache(user) -> dict:
    """Lazy per-request cache stored on the user object."""
    if not hasattr(user, "_profile_cache"):
        user._profile_cache = {}
    return user._profile_cache


def get_profile(user, profile_type: str):
    from accounts.models import ProfileBase

    pt = normalize_profile_type(profile_type)
    if not user or not getattr(user, "is_authenticated", False) or not pt:
        return None

    cache = _profile_cache(user)

    _SENTINEL = object()  # defined at module level ideally
    cached = cache.get(pt, _SENTINEL)
    if cached is not _SENTINEL:
        return cached  # returns None if explicitly cached as missing

    result = None

    if pt == PROFILE_CUSTOMER:
        base = (
            ProfileBase.objects.filter(user=user, profile_type=PROFILE_CUSTOMER)
            .select_related("customer_profile")
            .first()
        )
        result = getattr(base, "customer_profile", None) if base else None

    elif pt == PROFILE_DRIVER:
        base = (
            ProfileBase.objects.filter(user=user, profile_type=PROFILE_DRIVER)
            .select_related("driver_profile")
            .first()
        )
        result = getattr(base, "driver_profile", None) if base else None

    elif pt == PROFILE_BUSINESS_ADMIN:
        try:
            result = user.business_admin
        except ObjectDoesNotExist:
            result = None

    elif pt == PROFILE_BUSINESS_STAFF:
        try:
            result = user.primary_agent
        except ObjectDoesNotExist:
            result = None

    elif pt == PROFILE_APP_ADMIN:
        try:
            result = user.app_admin
        except ObjectDoesNotExist:
            result = None

    cache[pt] = result  # cache None too — explicit miss
    return result
