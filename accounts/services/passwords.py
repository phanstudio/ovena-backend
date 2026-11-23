from __future__ import annotations

from accounts.services.profiles import (
    PROFILE_APP_ADMIN,
    PROFILE_BUSINESS_ADMIN,
    PROFILE_BUSINESS_STAFF,
    PROFILE_CUSTOMER,
    PROFILE_DRIVER,
    get_profile,
    normalize_profile_type,
)

ALL_PASSWORD_PROFILE_TYPES = (
    PROFILE_CUSTOMER,
    PROFILE_DRIVER,
    PROFILE_BUSINESS_ADMIN,
    PROFILE_BUSINESS_STAFF,
    PROFILE_APP_ADMIN,
)


def resolve_request_profile_type(request) -> str | None:
    """Extract normalized active_profile from request.auth or request/user attributes."""
    auth = getattr(request, "auth", None)
    if auth is not None and hasattr(auth, "get"):
        token_profile = normalize_profile_type(auth.get("active_profile"))
        if token_profile:
            return token_profile

    req_profile = normalize_profile_type(getattr(request, "active_profile", None))
    if req_profile:
        return req_profile

    user = getattr(request, "user", None)
    if user is not None:
        return normalize_profile_type(getattr(user, "active_profile", None))

    return None


def profile_has_usable_password(user, profile_type: str | None) -> bool:
    """
    Returns True if the specified profile has a usable password_hash.
    If profile_type is None, falls back to User.has_usable_password().
    """
    pt = normalize_profile_type(profile_type)
    if not pt:
        return bool(user and user.has_usable_password())

    profile = get_profile(user, pt)
    if not profile:
        return False
    return bool(getattr(profile, "has_usable_password", False))


def check_profile_password(user, profile_type: str | None, raw_password: str) -> bool:
    """
    Verify raw_password against the profile's own password_hash.
    Falls back to legacy User.password ONLY if profile.password_hash is empty
    (and lazily backfills profile.password_hash on match).
    """
    if not user or not raw_password:
        return False

    pt = normalize_profile_type(profile_type)
    if not pt:
        return user.check_password(raw_password)

    profile = get_profile(user, pt)
    if not profile:
        return False

    if getattr(profile, "password_hash", ""):
        return profile.check_password(raw_password)

    # Legacy fallback for pre-migration rows that still only have User.password
    if pt != PROFILE_CUSTOMER and user.has_usable_password() and user.check_password(raw_password):
        profile.password_hash = user.password
        profile.save(update_fields=["password_hash"])
        return True

    return False


def set_profile_password(user, profile_type: str | None, raw_password: str) -> bool:
    """
    Set password on the specified profile without modifying User.password
    (so other profiles on the same User remain isolated).
    Returns True if a profile (or fallback User) was updated, False if profile not found.
    """
    pt = normalize_profile_type(profile_type)
    if not pt:
        user.set_password(raw_password)
        user.save(update_fields=["password"])
        return True

    profile = get_profile(user, pt)
    if not profile:
        return False

    profile.set_password(raw_password)
    profile.save(update_fields=["password_hash"])
    return True


def get_passworded_profiles(user) -> list[str]:
    """Return all profile types on user that have a usable profile password."""
    result: list[str] = []
    for pt in ALL_PASSWORD_PROFILE_TYPES:
        profile = get_profile(user, pt)
        if profile and getattr(profile, "has_usable_password", False):
            result.append(pt)
    return result


def get_existing_profiles(user) -> list[str]:
    """Return all profile types currently attached to user."""
    result: list[str] = []
    for pt in ALL_PASSWORD_PROFILE_TYPES:
        if get_profile(user, pt) is not None:
            result.append(pt)
    return result
