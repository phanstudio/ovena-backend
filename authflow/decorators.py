from .authentication import CustomJWTAuthentication
from .permissions import ScopePermission

def subuser_authentication(view_class): # turn to a mixin later
    """
    Class decorator to apply CustomJWTAuthentication + IsAuthenticated
    to any APIView subclass.
    """
    class Wrapped(view_class):
        authentication_classes = [CustomJWTAuthentication]
        permission_classes = [ScopePermission]
        required_scopes = []

    return Wrapped
