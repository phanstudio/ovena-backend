from rest_framework import permissions
from accounts.services.roles import (
    has_role, PROFILE_CUSTOMER, PROFILE_BUSINESS_ADMIN, PROFILE_DRIVER, PROFILE_BUSINESS_STAFF, PROFILE_APP_ADMIN
)

class IsCustomer(permissions.BasePermission): 
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_role(request, PROFILE_CUSTOMER)

class IsDriver(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_role(request, PROFILE_DRIVER)

class IsBusinessAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_role(request, PROFILE_BUSINESS_ADMIN)

class IsAppAdmin(permissions.BasePermission): # might add role based restriction like admin, support.
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_role(request, PROFILE_APP_ADMIN)

class IsBusinessStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and valid_staff(request)

class IsBusinessAgent(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        
        if valid_staff(request):
            request.actor_type = "staff"
            return True
        
        if has_role(request, PROFILE_BUSINESS_ADMIN):
            request.actor_type = "admin"
            return True
        return False

def valid_staff(request): # can i return revoked
    primaryagent = getattr(request.user, "primaryagent", None)
    return bool(
        primaryagent
        and not primaryagent.revoked
        and has_role(request, PROFILE_BUSINESS_STAFF)
    )