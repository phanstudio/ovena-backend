import secrets
import string
from decimal import Decimal
from django.db.models import Q
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound

from accounts.models import User
from admin_api.models import AppAdmin
from admin_api.serializers import (
    AdminUserListSerializer,
    AdminDriverListSerializer,
    AdminBusinessListSerializer,
    AppAdminProfileSerializer,
    AdminUserStatusSerializer,
    AdminUserPasswordResetSerializer,
    AdminCustomerWalletCreditSerializer,
)
from accounts.serializers import main_serializers as main_serial
from payments.services.split_calculator import _create_ledger_entry
from .base import BaseAppAdminAPIView, _AppAdminRoleGuardMixin


class AdminUserListView(BaseAppAdminAPIView, ListAPIView):
    """
    GET /api/admin/users/
    List users with search (q=email/name/phone) and role filtering.
    """
    serializer_class = AdminUserListSerializer

    def get_queryset(self):
        qs = User.objects.all().order_by("-id")
        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(email__icontains=q)
                | Q(phone_number__icontains=q)
            )

        role = (self.request.query_params.get("role") or "").strip().lower()
        if role == "drivers":
            qs = qs.filter(driver_profile__isnull=False)
        elif role == "customers":
            qs = qs.filter(customer_profile__isnull=False)
        elif role == "business_admins":
            qs = qs.filter(business_admin__isnull=False)
        elif role == "app_admins":
            qs = qs.filter(app_admin__isnull=False)

        return qs.distinct()


class AdminUserDetailView(BaseAppAdminAPIView):
    """
    GET /api/admin/users/<user_id>/
    Detailed profile breakdown for a single user across all roles.
    """

    def get(self, request, user_id: int):
        user = User.objects.filter(id=user_id).first()
        if not user:
            raise NotFound("User not found")

        payload = {
            "user": AdminUserListSerializer(user).data,
            "profiles": {
                "customer": bool(getattr(user, "customer_profile", None)),
                "driver": bool(getattr(user, "driver_profile", None)),
                "business_admin": bool(getattr(user, "business_admin", None)),
                "business_staff": bool(getattr(user, "primary_agent", None)),
                "app_admin": bool(getattr(user, "app_admin", None)),
            },
        }

        if getattr(user, "driver_profile", None):
            payload["driver_profile"] = AdminDriverListSerializer(user.driver_profile).data
        if getattr(user, "business_admin", None) and getattr(user.business_admin, "business", None):
            payload["business"] = AdminBusinessListSerializer(user.business_admin.business).data
        if getattr(user, "customer_profile", None):
            payload["customer_profile"] = main_serial.CustomerProfileSerializer(
                user.customer_profile, context={"user": user}
            ).data
        if getattr(user, "app_admin", None):
            payload["app_admin"] = AppAdminProfileSerializer(user.app_admin).data
        if getattr(user, "primary_agent", None):
            payload["business_staff"] = main_serial.PrimaryAgentProfileSerializer(user.primary_agent).data

        return Response(payload)


class AdminUserStatusView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """
    PATCH /api/admin/users/<user_id>/status/
    Suspend or reactivate user account (toggles is_active).
    """
    allowed_roles = {AppAdmin.Role.SUPERVISOR, AppAdmin.Role.ADMIN, AppAdmin.Role.OWNER, AppAdmin.Role.OPERATIONS}
    serializer_class = AdminUserStatusSerializer

    def patch(self, request, user_id: int):
        self._require_app_admin_roles(request, self.allowed_roles)
        user = User.objects.filter(id=user_id).first()
        if not user:
            raise NotFound("User not found")

        vd = self.validate_serializer(request.data)
        user.is_active = vd["is_active"]
        user.save(update_fields=["is_active"])

        status_text = "active" if user.is_active else "suspended"
        return Response({
            "detail": f"User account has been {status_text}",
            "user_id": user.id,
            "is_active": user.is_active,
            "reason": vd.get("reason", ""),
        })


class AdminUserPasswordResetView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """
    POST /api/admin/users/<user_id>/reset-password/
    Admin-initiated password reset for user account.
    """
    allowed_roles = {AppAdmin.Role.SUPPORT, AppAdmin.Role.SUPERVISOR, AppAdmin.Role.ADMIN, AppAdmin.Role.OWNER}
    serializer_class = AdminUserPasswordResetSerializer

    def post(self, request, user_id: int):
        self._require_app_admin_roles(request, self.allowed_roles)
        user = User.objects.filter(id=user_id).first()
        if not user:
            raise NotFound("User not found")

        vd = self.validate_serializer(request.data)
        new_password = vd.get("new_password")
        if not new_password:
            chars = string.ascii_letters + string.digits + "!@#$%"
            new_password = "".join(secrets.choice(chars) for _ in range(12))

        user.set_password(new_password)
        user.save(update_fields=["password"])

        return Response({
            "detail": "User password reset successfully",
            "user_id": user.id,
            "temporary_password": new_password,
        })


class AdminCustomerWalletCreditView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """
    POST /api/admin/users/<user_id>/credit-wallet/
    Admin manually credits customer wallet with an audited ledger entry.
    """
    allowed_roles = {AppAdmin.Role.FINANCE, AppAdmin.Role.ADMIN, AppAdmin.Role.OWNER}
    serializer_class = AdminCustomerWalletCreditSerializer

    def post(self, request, user_id: int):
        self._require_app_admin_roles(request, self.allowed_roles)
        user = User.objects.filter(id=user_id).first()
        if not user:
            raise NotFound("User not found")

        vd = self.validate_serializer(request.data)
        amount_kobo = int(vd["amount_ngn"] * Decimal("100"))
        reason = vd["reason"]
        notes = vd.get("notes") or f"Admin manual credit by {request.user.id}: {reason}"

        entry = _create_ledger_entry(
            user=user,
            sale=None,
            role="customer",
            entry_type="credit",
            amount=amount_kobo,
            notes=notes,
        )

        return Response({
            "detail": "Customer wallet credited successfully",
            "user_id": user.id,
            "amount_ngn": vd["amount_ngn"],
            "balance_after_ngn": Decimal(entry.balance_after) / Decimal("100"),
            "ledger_entry_id": str(entry.id),
        }, status=status.HTTP_201_CREATED)
