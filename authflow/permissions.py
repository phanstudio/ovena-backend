from rest_framework import permissions
from accounts.services.roles import has_role, PROFILE_CUSTOMER, PROFILE_BUSINESS_ADMIN, PROFILE_DRIVER, PROFILE_BUSINESS_STAFF

class IsCustomer(permissions.BasePermission): 
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_role(request, PROFILE_CUSTOMER)

class IsDriver(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_role(request, PROFILE_DRIVER)

class IsBusinessAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_role(request, PROFILE_BUSINESS_ADMIN)

class IsBusinessStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and valid_staff(request)

class IsBusinessAgent(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            valid_staff(request) or has_role(request, PROFILE_BUSINESS_ADMIN)
        )

def valid_staff(request): # can i return revoked
    return (not request.user.primary_agent.revoked and has_role(request, PROFILE_BUSINESS_STAFF))