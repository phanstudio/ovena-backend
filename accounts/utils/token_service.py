from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import User

def _issue_jwt_for_user(user: User):
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }