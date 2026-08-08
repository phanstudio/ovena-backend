from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import User, Suspension
from accounts.services.roles import get_user_roles
from payments.models.subscription import Subscription
from accounts.services.profiles import (
    PROFILE_DRIVER,
)

def issue_jwt_for_user(user: User, *, active_profile: str | None = None, plan_id = None):
    refresh = RefreshToken.for_user(user)
    if active_profile:
        refresh["active_profile"] = active_profile

    refresh["plan_id"] = plan_id or None

    check_suspension(user, active_profile, refresh)

    refresh.access_token["active_profile"] = active_profile
    refresh.access_token["plan_id"] = plan_id or None
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }

def issue_jwt_for_user_with_plan(user: User, *, active_profile: str | None = None):
    sub = Subscription.objects.filter(user=user, active=True).first()
    plan_id = None
    if sub:
        plan_id = sub.plan.id
    return issue_jwt_for_user(user, active_profile=active_profile, plan_id=plan_id)

def check_suspension(user: User, active_profile, refresh) -> Suspension:
    if active_profile in [PROFILE_DRIVER]:
        is_suspended = Suspension.objects.filter(user=user, lifted_at=None).exists()
        refresh.access_token["suspended"] = is_suspended
