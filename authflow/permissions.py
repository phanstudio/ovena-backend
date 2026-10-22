from rest_framework import permissions
from accounts.services.roles import (
    has_role,
    PROFILE_CUSTOMER,
    PROFILE_BUSINESS_ADMIN,
    PROFILE_DRIVER,
    PROFILE_BUSINESS_STAFF,
    PROFILE_APP_ADMIN,
)
from .subscritpion import get_all_features
from accounts.services.suspensions import is_suspended


class NeedsApprovalPermission(permissions.BasePermission):
    message = "User account not approved."

    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and self.needs_approval(request))
    
    def needs_approval(self, request):
        if request.auth and hasattr(request.auth, "get") and "is_approved" in request.auth:
            return bool(request.auth.get("is_approved"))
        return bool(getattr(request.user, "is_approved", True))


class NeedsVerficationsPermission(permissions.BasePermission):
    message = "Business verification or onboarding incomplete."

    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and self.needs_approval(request))
    
    def needs_approval(self, request):
        if request.auth and hasattr(request.auth, "get") and "is_approved" in request.auth:
            return bool(request.auth.get("is_approved"))
        business_admin = getattr(request.user, "business_admin", None)
        business = getattr(business_admin, "business", None) if business_admin else None
        if not business:
            primary_agent = getattr(request.user, "primary_agent", None)
            if primary_agent and getattr(primary_agent, "branch", None):
                business = primary_agent.branch.business
        if business:
            return bool(business.onboarding_complete)
        return False


class IsNotSuspended(permissions.BasePermission):
    message = "Your account has been suspended."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if request.auth and hasattr(request.auth, "get") and "suspended" in request.auth:
            if request.auth.get("suspended") is True:
                return False
            return True

        active_profile = None
        if request.auth and hasattr(request.auth, "get"):
            active_profile = request.auth.get("active_profile")
        if not active_profile:
            active_profile = getattr(request, "active_profile", None)

        return not is_suspended(user.id, role=active_profile)



class IsCustomer(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_role(request, PROFILE_CUSTOMER)


class IsDriver(NeedsApprovalPermission):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and has_role(request, PROFILE_DRIVER)


class IsDriverWithoutApproval(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_role(request, PROFILE_DRIVER)


class IsBusinessAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_role(
            request, PROFILE_BUSINESS_ADMIN
        )


# might add role based restriction like admin, support.
class IsAppAdmin(permissions.BasePermission):  
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_role(request, PROFILE_APP_ADMIN)


class IsBusinessStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        valid_staff = validate_staff(request)
        if not valid_staff:
            self.message = "Staff access revoked or not a valid staff member."
        return request.user.is_authenticated and valid_staff


class IsBusinessAgent(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if validate_staff(request):
            request.actor_type = "staff"
            return True

        if has_role(request, PROFILE_BUSINESS_ADMIN):
            request.actor_type = "admin"
            return True
        return False


def validate_staff(request):  # can i return revoked
    primary_agent = getattr(request.user, "primary_agent", None)
    return bool(
        primary_agent
        and not primary_agent.revoked
        and has_role(request, PROFILE_BUSINESS_STAFF)
    )

class HasFeature(permissions.BasePermission):
    message = "Your subscription plan does not have access to this feature."

    def check_feature(self, token_features, required_features):
        return all(feature in token_features for feature in required_features)

    def has_permission(self, request, view):
        required_feature = getattr(view, "required_feature", [])
        if not required_feature:
            return True

        if not request.auth or not hasattr(request.auth, "get"):
            return False

        plan_id = request.auth.get("plan_id")
        if not plan_id and isinstance(request.auth.get("plan_info"), dict):
            plan_id = request.auth.get("plan_info", {}).get("plan_id")

        if not plan_id:
            return False

        plan_features = get_all_features(plan_id)
        return self.check_feature(plan_features, required_feature)

