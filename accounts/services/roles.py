from __future__ import annotations

from typing import Set
from accounts.services.profiles import (
    PROFILE_BUSINESS_ADMIN,
    PROFILE_BUSINESS_STAFF,
    PROFILE_CUSTOMER,
    PROFILE_DRIVER,
    has_profile,
)


LEGACY_ROLE_ALIASES = {
    "buisnessstaff": "businessstaff",
    "restaurantstaff": "businessstaff",
}


def _normalize_role(role: str | None) -> str | None:
    if not role:
        return None
    return LEGACY_ROLE_ALIASES.get(role, role)


def get_user_roles(user) -> Set[str]:
    """
    Derived roles are source-of-truth. Legacy user.role is fallback-only.
    """
    roles: Set[str] = set()

    if not user or not getattr(user, "is_authenticated", False):
        return roles

    if has_profile(user, PROFILE_CUSTOMER):
        roles.add(PROFILE_CUSTOMER)
    if has_profile(user, PROFILE_DRIVER):
        roles.add(PROFILE_DRIVER)
    if has_profile(user, PROFILE_BUSINESS_ADMIN):
        roles.add(PROFILE_BUSINESS_ADMIN)
    if has_profile(user, PROFILE_BUSINESS_STAFF):
        roles.add(PROFILE_BUSINESS_STAFF)

    legacy = _normalize_role(getattr(user, "role", None))
    if legacy:
        roles.add(legacy)

    return roles


def has_role_all(user, role: str) -> bool:
    normalized_target = _normalize_role(role)
    return normalized_target in get_user_roles(user)

def has_role(request, role: str) -> bool:
    active_profile = request.auth.get("active_profile")
    return active_profile == role

# def _check_single_role(user, role: str) -> bool:
#     if role in (PROFILE_CUSTOMER, PROFILE_DRIVER, PROFILE_BUSINESS_ADMIN, PROFILE_BUSINESS_STAFF):
#         return has_profile(user, role)  # uses profile cache
#     # fallback to legacy user.role field
#     return _normalize_role(getattr(user, "role", None)) == role
