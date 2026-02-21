from rest_framework import permissions

class ScopePermission(permissions.BasePermission):
    """
    Checks whether the token includes the required scope(s).
    Usage:
        permission_classes = [ScopePermission]
        required_scopes = ["read"]
    """
    def get_scopes(self, request):
        return request.auth.get("scopes", set()) if request.auth else set()
    
    def check_scope(self, token_scopes, required_scopes):
        return all(scope in token_scopes for scope in required_scopes) or token_scopes == {"*"}

    def has_permission(self, request, view):
        required_scopes = getattr(view, "required_scopes", [])
        return self.check_scope(self.get_scopes(request), required_scopes)

class ReadScopePermission(ScopePermission):
    def has_permission(self, request, view):
        return (
            request.method in permissions.SAFE_METHODS and 
            self.check_scope(self.get_scopes(request), {"read"})
        )


class IsCustomer(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "customer"

class IsDriver(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "driver"

class IsBusinessAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "businessadmin"
