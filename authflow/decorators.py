from .authentication import CustomJWTAuthentication
from .permissions import ScopePermission
from accounts.models import LinkedStaff, User

# ApiViews add later
def subuser_authentication(view_class): # turn to a mixin later
    """
    Class decorator to apply CustomJWTAuthentication + IsAuthenticated
    to any APIView subclass.
    """
    class Wrapped(view_class):
        authentication_classes = [CustomJWTAuthentication]
        permission_classes = [ScopePermission]
        required_scopes = []

        def get_linkeduser(self):
            user = self.request.user
            primaryagent = None
            if isinstance(user, LinkedStaff):
                primaryagent =  user.created_by
            if isinstance(user, User):
                primaryagent=user.primaryagent
            return user, primaryagent

    return Wrapped
