from rest_framework.pagination import LimitOffsetPagination
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import NotFound, PermissionDenied
from drf_spectacular.utils import extend_schema

from admin_api.models import AppAdmin
from admin_api.serializers import (
    LoginResponseSerializer,
    AppAdminLoginSerializer,
    UserSerializer,
    AppAdminProfileSerializer,
    UpdateAppAdminSerializer,
)
from authflow.permissions import IsAppAdmin
from authflow.authentication import CustomAppAdminAuth
from accounts.views.account_views import LoginView
from accounts.services.profiles import PROFILE_APP_ADMIN


class AdminPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100


class BaseAppAdminAPIView(GenericAPIView):
    authentication_classes = [CustomAppAdminAuth]
    permission_classes = [IsAppAdmin]
    pagination_class = AdminPagination

    def get_app_admin(self, request) -> AppAdmin:
        try:
            return request.user.app_admin
        except AppAdmin.DoesNotExist:
            raise NotFound("App admin profile not found")

    def validate_serializer(self, data=None, *, context=None):
        serializer_class = self.get_serializer_class()
        if not serializer_class:
            raise AssertionError("No serializer_class defined for this view")

        serializer = serializer_class(
            data=data or self.request.data,
            context=context or self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class _AppAdminRoleGuardMixin:
    """Simple role-gate for sensitive admin actions."""
    allowed_roles: set[str] = set()

    def _require_app_admin_roles(self, request, roles: set[str]):
        try:
            app_admin = request.user.app_admin
        except Exception:
            raise PermissionDenied("App admin profile not found")
        if app_admin.role not in roles:
            raise PermissionDenied("Insufficient privileges for this action")


@extend_schema(responses={200: LoginResponseSerializer}, auth=[])
class AdminLoginView(LoginView):
    permission_classes = [AllowAny]
    serializer_class = AppAdminLoginSerializer

    def get_profile_type(self):
        return PROFILE_APP_ADMIN


class UserProfileView(BaseAppAdminAPIView):
    def get(self, request):
        user = request.user
        return Response(
            {
                "user": UserSerializer(user).data,
                "profile": AppAdminProfileSerializer(user.app_admin).data,
            }
        )


class UpdateAppAdmin(BaseAppAdminAPIView):
    def patch(self, request):
        serializer = UpdateAppAdminSerializer(
            instance=request.user.app_admin,
            data=request.data,
            context={"user": request.user},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Profile updated successfully"},
            status=status.HTTP_200_OK,
        )
