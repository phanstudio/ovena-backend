from rest_framework import permissions

class ScopePermission(permissions.BasePermission):
    """
    Checks whether the token includes the required scope(s).
    Usage:
        permission_classes = [ScopePermission]
        required_scopes = ["read"]
    """
    def check_scope(self, request, required_scopes):
        token_scopes = request.auth.get("scopes", set()) if request.auth else set()
        return all(scope in token_scopes for scope in required_scopes) or token_scopes == {"*"}
    
    def has_permission(self, request, view):
        required_scopes = getattr(view, "required_scopes", [])
        return self.check_scope(request, required_scopes)

class ReadScopePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        required_scope = "read"
        token_scopes = request.auth.get("scopes", set()) if request.auth else set()
        return (required_scope in token_scopes and request.method in permissions.SAFE_METHODS) or token_scopes == {"*"}
