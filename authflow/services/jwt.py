from __future__ import annotations

import logging
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.exceptions import AuthenticationFailed, TokenError

from accounts.models import User, Suspension
from payments.models.subscription import Subscription
from accounts.services.profiles import (
    PROFILE_DRIVER,
    PROFILE_BUSINESS_ADMIN,
    PROFILE_BUSINESS_STAFF,
    PROFILE_CUSTOMER,
    PROFILE_APP_ADMIN,
    has_profile,
    normalize_profile_type,
    get_default_profile_for_user,
)
from accounts.services.suspensions import is_suspended

logger = logging.getLogger(__name__)


def compute_is_approved(user: User, active_profile: str | None) -> bool:
    """
    Compute approval status per active profile identity:
    - Driver: user.is_approved
    - Business Admin: business exists and business.onboarding_complete
    - Business Staff: primary agent not revoked
    - Customer / App Admin: True
    """
    pt = normalize_profile_type(active_profile)

    if pt == PROFILE_DRIVER:
        return bool(getattr(user, "is_approved", False))

    if pt == PROFILE_BUSINESS_ADMIN:
        business_admin = getattr(user, "business_admin", None)
        business = getattr(business_admin, "business", None) if business_admin else None
        return bool(business and getattr(business, "onboarding_complete", False))

    if pt == PROFILE_BUSINESS_STAFF:
        primary_agent = getattr(user, "primary_agent", None)
        return bool(primary_agent and not getattr(primary_agent, "revoked", False))

    if pt in (PROFILE_CUSTOMER, PROFILE_APP_ADMIN):
        return True

    return bool(getattr(user, "is_approved", True))


def build_jwt_claims(user: User, *, active_profile: str | None = None, plan_id: int | None = None) -> dict:
    """
    Build standardized claims dictionary for a locked user identity.
    """
    resolved_profile = active_profile or get_default_profile_for_user(user)
    normalized_profile = normalize_profile_type(resolved_profile)

    suspended = is_suspended(user.id, role=normalized_profile) if user and user.id else False
    approved = compute_is_approved(user, normalized_profile)

    return {
        "active_profile": normalized_profile,
        "plan_id": plan_id or None,
        "is_approved": approved,
        "is_active": bool(getattr(user, "is_active", True)),
        "suspended": suspended,
    }


def issue_jwt_for_user(user: User, *, active_profile: str | None = None, plan_id: int | None = None) -> dict:
    """
    Issue JWT access and refresh token pair locked to a specific active profile.
    """
    if not user.is_active:
        raise AuthenticationFailed(_("User is inactive"), code="user_inactive")

    claims = build_jwt_claims(user, active_profile=active_profile, plan_id=plan_id)
    refresh = RefreshToken.for_user(user)

    for k, v in claims.items():
        refresh[k] = v
        refresh.access_token[k] = v

    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def issue_jwt_for_user_with_plan(user: User, *, active_profile: str | None = None) -> dict:
    """
    Fetch user's active subscription plan from DB and issue JWT tokens locked to active_profile.
    """
    sub = Subscription.objects.filter(user=user, active=True).first()
    plan_id = sub.plan.id if (sub and sub.plan) else None
    return issue_jwt_for_user(user, active_profile=active_profile, plan_id=plan_id)


def refresh_jwt_tokens(refresh_token_str: str) -> dict:
    """
    Refresh JWT tokens while preserving locked identity (active_profile).
    Re-queries latest subscription, approval, and suspension status from DB.
    Rotates and blacklists old refresh token according to settings.
    """
    if not refresh_token_str:
        raise AuthenticationFailed(_("Refresh token required"), code="token_required")

    try:
        old_refresh = RefreshToken(refresh_token_str)
    except TokenError as e:
        raise AuthenticationFailed(str(e), code="token_invalid")

    user_id = old_refresh.get(api_settings.USER_ID_CLAIM)
    if not user_id:
        raise AuthenticationFailed(_("Token contained no recognizable user identification"), code="user_not_found")

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        raise AuthenticationFailed(_("User not found"), code="user_not_found")

    if not user.is_active:
        raise AuthenticationFailed(_("User is inactive"), code="user_inactive")

    # Lock to original active_profile from the refresh token
    active_profile = old_refresh.get("active_profile")
    if not active_profile:
        # Backward compatibility for legacy tokens
        active_profile = get_default_profile_for_user(user)

    normalized_profile = normalize_profile_type(active_profile)
    if normalized_profile and not has_profile(user, normalized_profile):
        raise AuthenticationFailed(
            _("Profile '%(profile)s' is no longer valid for this account") % {"profile": normalized_profile},
            code="profile_invalid",
        )

    # Re-evaluate latest plan from DB
    sub = Subscription.objects.filter(user=user, active=True).first()
    plan_id = sub.plan.id if (sub and sub.plan) else None

    # Re-evaluate claims with fresh DB values
    claims = build_jwt_claims(user, active_profile=normalized_profile, plan_id=plan_id)

    if api_settings.ROTATE_REFRESH_TOKENS:
        new_refresh = RefreshToken.for_user(user)
        for k, v in claims.items():
            new_refresh[k] = v
            new_refresh.access_token[k] = v

        if api_settings.BLACKLIST_AFTER_ROTATION:
            try:
                old_refresh.blacklist()
            except Exception as e:
                logger.warning("Could not blacklist old refresh token: %s", e)

        return {
            "access": str(new_refresh.access_token),
            "refresh": str(new_refresh),
        }
    else:
        access_token = old_refresh.access_token
        for k, v in claims.items():
            access_token[k] = v
        return {
            "access": str(access_token),
            "refresh": refresh_token_str,
        }


def check_suspension(user: User, active_profile: str | None, refresh) -> bool:
    """
    Backward compatibility helper.
    """
    suspended = is_suspended(user.id, role=active_profile) if user and user.id else False
    refresh.access_token["suspended"] = suspended
    return suspended
