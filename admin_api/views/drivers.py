from django.db.models import Count, Q, OuterRef, Subquery
from django.utils import timezone
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound

from accounts.models import User, DriverProfile
from accounts.models.driver import DriverOnboardingSubmission, DriverDocument
from admin_api.models import AppAdmin
from admin_api.serializers import (
    AdminDriverListSerializer,
    AdminDriverStatusSerializer,
    AdminDriverDocumentReviewSerializer,
)
from .base import BaseAppAdminAPIView, _AppAdminRoleGuardMixin


class AdminDriverListView(BaseAppAdminAPIView, ListAPIView):
    """
    GET /api/admin/employees/drivers/
    List drivers with online/busy filters, pending document counts, vehicle details.
    """
    serializer_class = AdminDriverListSerializer

    def get_queryset(self):
        latest = DriverOnboardingSubmission.objects.filter(
            driver=OuterRef("pk")
        ).order_by("-created_at")
        qs = (
            DriverProfile.objects.select_related("user")
            .annotate(
                pending_documents_count=Count(
                    "documents",
                    filter=Q(documents__status=DriverDocument.STATUS_PENDING),
                    distinct=True,
                ),
                pending_onboarding_submissions_count=Count(
                    "onboarding_submissions",
                    filter=Q(
                        onboarding_submissions__status=DriverOnboardingSubmission.STATUS_SUBMITTED
                    ),
                    distinct=True,
                ),
                latest_onboarding_status=Subquery(latest.values("status")[:1]),
                latest_onboarding_submitted_at=Subquery(
                    latest.values("submitted_at")[:1]
                ),
            )
            .order_by("-created_at")
        )

        status_filter = (self.request.query_params.get("status") or "").strip().lower()
        if status_filter == "online":
            qs = qs.filter(is_online=True)
        elif status_filter == "offline":
            qs = qs.filter(is_online=False)
        elif status_filter == "available":
            qs = qs.filter(is_online=True, is_available=True)
        elif status_filter == "busy":
            qs = qs.filter(is_online=True, is_available=False)

        return qs


class AdminDriverOnboardingReviewView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """
    POST /api/admin/employees/drivers/<driver_id>/onboarding/review/
    Approve/reject the most recent submitted onboarding submission for a driver.
    """
    allowed_roles = {
        AppAdmin.Role.SUPPORT,
        AppAdmin.Role.SUPERVISOR,
        AppAdmin.Role.ADMIN,
        AppAdmin.Role.OPERATIONS,
        AppAdmin.Role.OWNER,
    }

    def post(self, request, driver_id: int):
        self._require_app_admin_roles(request, self.allowed_roles)

        driver = (
            DriverProfile.objects.filter(id=driver_id).select_related("user").first()
        )
        if not driver:
            raise NotFound("Driver not found")

        decision = (request.data.get("status") or "").strip().lower()
        note = (request.data.get("reviewer_note") or "").strip()

        if decision not in {
            DriverOnboardingSubmission.STATUS_APPROVED,
            DriverOnboardingSubmission.STATUS_REJECTED,
        }:
            return Response(
                {"error": "Invalid status. Use 'approved' or 'rejected'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        submission = (
            DriverOnboardingSubmission.objects.filter(
                driver=driver, status=DriverOnboardingSubmission.STATUS_SUBMITTED
            )
            .order_by("-submitted_at", "-created_at")
            .first()
        )
        if not submission:
            raise NotFound("No submitted onboarding found for this driver")

        submission.status = decision
        submission.reviewed_by = request.user
        submission.reviewer_note = note
        submission.reviewed_at = timezone.now()
        submission.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewer_note",
                "reviewed_at",
                "updated_at",
            ]
        )

        return Response(
            {
                "detail": "Driver onboarding reviewed",
                "driver_id": driver.id,
                "submission_id": submission.id,
                "status": submission.status,
            }
        )


class ApproveDriverView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """
    POST /api/admin/employees/drivers/<driver_id>/approve/
    Directly approve driver profile.
    """
    allowed_roles = {AppAdmin.Role.SUPERVISOR, AppAdmin.Role.ADMIN, AppAdmin.Role.OPERATIONS, AppAdmin.Role.OWNER}

    def post(self, request, driver_id: int):
        self._require_app_admin_roles(request, self.allowed_roles)
        updated = User.objects.filter(driver_profile__id=driver_id).update(is_approved=True)
        if updated == 0:
            raise NotFound("Driver not found")

        return Response({"detail": "Driver approved", "is_approved": True})


class AdminDriverStatusView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """
    POST /api/admin/employees/drivers/<driver_id>/status/
    Manage driver status: approve, suspend, block, activate.
    """
    allowed_roles = {AppAdmin.Role.SUPERVISOR, AppAdmin.Role.ADMIN, AppAdmin.Role.OPERATIONS, AppAdmin.Role.OWNER}
    serializer_class = AdminDriverStatusSerializer

    def post(self, request, driver_id: int):
        self._require_app_admin_roles(request, self.allowed_roles)
        driver = DriverProfile.objects.filter(id=driver_id).select_related("user").first()
        if not driver:
            raise NotFound("Driver not found")

        vd = self.validate_serializer(request.data)
        action = vd["action"]
        user = driver.user

        if action == "approve":
            user.is_approved = True
            user.is_active = True
        elif action in {"suspend", "block"}:
            user.is_active = False
            driver.is_online = False
            driver.is_available = False
            driver.save(update_fields=["is_online", "is_available"])
        elif action == "activate":
            user.is_active = True

        user.save(update_fields=["is_active", "is_approved"])
        return Response({
            "detail": f"Driver action '{action}' applied successfully",
            "driver_id": driver.id,
            "is_active": user.is_active,
            "is_approved": user.is_approved,
            "reason": vd.get("reason", ""),
        })


class AdminDriverDocumentReviewView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """
    POST /api/admin/employees/drivers/<driver_id>/documents/<document_id>/review/
    Approve or reject a specific driver document (bag, selfie, license).
    """
    allowed_roles = {AppAdmin.Role.SUPPORT, AppAdmin.Role.SUPERVISOR, AppAdmin.Role.ADMIN, AppAdmin.Role.OPERATIONS, AppAdmin.Role.OWNER}
    serializer_class = AdminDriverDocumentReviewSerializer

    def post(self, request, driver_id: int, document_id: int):
        self._require_app_admin_roles(request, self.allowed_roles)
        doc = DriverDocument.objects.filter(id=document_id, driver_id=driver_id).first()
        if not doc:
            raise NotFound("Driver document not found")

        vd = self.validate_serializer(request.data)
        doc.status = vd["status"]
        if vd.get("rejection_reason"):
            doc.rejection_reason = vd["rejection_reason"]
        doc.save(update_fields=["status", "rejection_reason"] if hasattr(doc, "rejection_reason") else ["status"])

        return Response({
            "detail": f"Document marked as {doc.status}",
            "driver_id": driver_id,
            "document_id": doc.id,
            "doc_type": doc.doc_type,
            "status": doc.status,
        })
