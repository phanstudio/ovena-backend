from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import User
from accounts.services.roles import get_user_roles
from payments.models.subscription import Subscription

def issue_jwt_for_user(user: User, *, active_profile: str | None = None, plan_id = None):
    refresh = RefreshToken.for_user(user)
    # refresh.access_token["roles"] = sorted(get_user_roles(user)) # we don't care about your regular roles when using the jwt
    if active_profile:
        refresh.access_token["active_profile"] = active_profile
    refresh.access_token["plan_id"] = plan_id or {}
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
