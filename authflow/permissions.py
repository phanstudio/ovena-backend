from rest_framework import permissions
from accounts.services.roles import (
    has_role,
    PROFILE_CUSTOMER,
    PROFILE_BUSINESS_ADMIN,
    PROFILE_DRIVER,
    PROFILE_BUSINESS_STAFF,
    PROFILE_APP_ADMIN,
)

class NeedsApprovalPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and self.needs_approval(request)
    
    def needs_approval(self, request):
        # approved = request.user.is_approved
        # if not approved:
        #     self.message = "User not approved"
        # return approved
        return True


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
