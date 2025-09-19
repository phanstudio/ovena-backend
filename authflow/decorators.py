from functools import wraps
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view
from rest_framework.views import APIView

from .authentication import CustomJWTAuthentication


def subuser_authentication(view_class):
    """
    Class decorator to apply CustomJWTAuthentication + IsAuthenticated
    to any APIView subclass.
    """
    class Wrapped(view_class):
        authentication_classes = [CustomJWTAuthentication]
        permission_classes = [IsAuthenticated]

    return Wrapped
