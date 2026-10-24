from decimal import Decimal
from django.db.models import Count, Q
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.exceptions import NotFound

from accounts.models import Business, Branch
from payments.models import PlatformConfig
from admin_api.models import AppAdmin
from admin_api.serializers import (
    AdminBusinessListSerializer,
    AdminBusinessUpdateSerializer,
    AdminBusinessStatusSerializer,
    AdminBusinessCommissionSerializer,
)
from .base import BaseAppAdminAPIView, _AppAdminRoleGuardMixin


class AdminBusinessListView(BaseAppAdminAPIView, ListAPIView):
    """
    GET /api/admin/employees/businesses/
    List businesses with branch counts, onboarding status, and search filters.
    """
    serializer_class = AdminBusinessListSerializer

    def get_queryset(self):
        qs = (
            Business.objects.select_related("admin__user")
            .annotate(branches_count=Count("branches", distinct=True))
            .order_by("-created_at")
        )

        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(business_name__icontains=q)
                | Q(email__icontains=q)
                | Q(phone_number__icontains=q)
            )

        onboarding = (
            (self.request.query_params.get("onboarding_complete") or "").strip().lower()
        )
        if onboarding in {"true", "false"}:
            qs = qs.filter(onboarding_complete=(onboarding == "true"))

        return qs


class AdminBusinessUpdateView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """
    PATCH /api/admin/employees/businesses/<business_id>/
    Update business onboarding status (review completion).
    """
    allowed_roles = {AppAdmin.Role.SUPERVISOR, AppAdmin.Role.ADMIN, AppAdmin.Role.OPERATIONS, AppAdmin.Role.OWNER}
    serializer_class = AdminBusinessUpdateSerializer

    def patch(self, request, business_id: int):
        self._require_app_admin_roles(request, self.allowed_roles)

        business = Business.objects.filter(id=business_id).first()
        if not business:
            raise NotFound("Business not found")

        vd = self.validate_serializer(request.data)
        updated_fields = []
        if "onboarding_complete" in vd:
            business.onboarding_complete = vd["onboarding_complete"]
            updated_fields.append("onboarding_complete")

        if updated_fields:
            business.save(update_fields=updated_fields)

        return Response(
            {
                "detail": "Business updated",
                "business": AdminBusinessListSerializer(business).data,
            }
        )


class AdminBusinessStatusView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """
    POST /api/admin/employees/businesses/<business_id>/status/
    Actions: approve, suspend, activate, feature, unfeature, hide, unhide.
    """
    allowed_roles = {AppAdmin.Role.SUPERVISOR, AppAdmin.Role.ADMIN, AppAdmin.Role.OPERATIONS, AppAdmin.Role.OWNER}
    serializer_class = AdminBusinessStatusSerializer

    def post(self, request, business_id: int):
        self._require_app_admin_roles(request, self.allowed_roles)
        business = Business.objects.filter(id=business_id).first()
        if not business:
            raise NotFound("Business not found")

        vd = self.validate_serializer(request.data)
        action = vd["action"]

        if action == "approve":
            business.onboarding_complete = True
            business.save(update_fields=["onboarding_complete"])
            Branch.objects.filter(business=business).update(is_active=True, is_accepting_orders=True)
        elif action in {"suspend", "hide"}:
            Branch.objects.filter(business=business).update(is_active=False, is_accepting_orders=False)
        elif action in {"activate", "unhide"}:
            Branch.objects.filter(business=business).update(is_active=True, is_accepting_orders=True)
        elif action == "feature":
            PlatformConfig.objects.update_or_create(
                key=f"featured_business_{business.id}",
                defaults={"value": "true", "description": f"Featured status for {business.business_name}"}
            )
        elif action == "unfeature":
            PlatformConfig.objects.filter(key=f"featured_business_{business.id}").delete()

        return Response({
            "detail": f"Action '{action}' executed for business {business.id}",
            "business_id": business.id,
            "business_name": business.business_name,
            "onboarding_complete": business.onboarding_complete,
            "reason": vd.get("reason", ""),
        })


class AdminBusinessCommissionView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """
    GET, POST /api/admin/employees/businesses/<business_id>/commission/
    View or override custom commission rate for a specific business/restaurant.
    """
    allowed_roles = {AppAdmin.Role.FINANCE, AppAdmin.Role.ADMIN, AppAdmin.Role.OWNER, AppAdmin.Role.OPERATIONS}
    serializer_class = AdminBusinessCommissionSerializer

    def get(self, request, business_id: int):
        business = Business.objects.filter(id=business_id).first()
        if not business:
            raise NotFound("Business not found")

        cfg = PlatformConfig.objects.filter(key=f"commission_business_{business.id}").first()
        rate = cfg.value if cfg else PlatformConfig.get("restaurant_commission_percent", default="10.0")

        return Response({
            "business_id": business.id,
            "business_name": business.business_name,
            "commission_rate": Decimal(rate),
            "is_custom": bool(cfg),
        })

    def post(self, request, business_id: int):
        self._require_app_admin_roles(request, self.allowed_roles)
        business = Business.objects.filter(id=business_id).first()
        if not business:
            raise NotFound("Business not found")

        vd = self.validate_serializer(request.data)
        rate = str(vd["commission_rate"])

        PlatformConfig.objects.update_or_create(
            key=f"commission_business_{business.id}",
            defaults={"value": rate, "description": f"Custom commission for {business.business_name}"}
        )

        return Response({
            "detail": "Commission rate updated",
            "business_id": business.id,
            "commission_rate": vd["commission_rate"],
        })
