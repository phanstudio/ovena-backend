from admin_api.models import AppAdmin
from accounts.models import User, DriverProfile, Business
from admin_api.serializers import (
    LoginResponseSerializer,
    AppAdminLoginSerializer,
    UserSerializer,
    AppAdminProfileSerializer,
    UpdateAppAdminSerializer,
    AdminUserListSerializer,
    AdminDriverListSerializer,
    AdminBusinessListSerializer,
    AdminBusinessUpdateSerializer,
    AdminWithdrawalSerializer,
    AdminWithdrawalMarkFailedSerializer,
    AdminSendNotificationSerializer,
)
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema  # type: ignore
from authflow.services import issue_jwt_for_user
from rest_framework.permissions import AllowAny
from rest_framework.generics import GenericAPIView, RetrieveAPIView, ListAPIView
from authflow.permissions import IsAppAdmin
from authflow.authentication import CustomAppAdminAuth
from rest_framework.exceptions import NotFound, PermissionDenied
from referrals.models import ReferralPayout
from referrals.serializers import ReferralPayoutSerializer
from referrals.services import verify_snapshot_integrity
from django.db.models import Sum, Count, Q, OuterRef, Subquery
from django.utils import timezone

from accounts.models.driver import DriverOnboardingSubmission, DriverDocument
from notifications.models import Notification
from notifications.serializers import NotificationSerializer
from notifications.services import create_notification, create_bulk_notifications

from payments.models import Withdrawal
from payments.payouts.services import mark_withdrawal_paid, mark_withdrawal_failed
from payments.payouts.tasks import (
    execute_batch_payouts,
    execute_realtime_withdrawal,
    retry_pending_withdrawals,
    reconcile_stale_processing_withdrawals,
)
from referrals.services import REFERRALS_PER_UNIT
from decimal import Decimal
from rest_framework.pagination import LimitOffsetPagination


class AdminPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100


# employee management i.e drivers and restaurants, users(i.e customers)
# see user need to referral payment and when
# see requests to withdraw
# notifications
# withdrawals system
# current number of users
# dashboard to see stats;

## pending
# check new driver and restaurants;
# send codes to create;


class BaseAppAdminAPIView(GenericAPIView):
    authentication_classes = [CustomAppAdminAuth]
    permission_classes = [IsAppAdmin]
    pagination_class = AdminPagination

    def get_app_admin(self, request) -> AppAdmin:
        try:
            return request.user.app_admin
        except AppAdmin.DoesNotExist:
            raise NotFound("App admin profile not found")

    # 🔥 NEW: safe serializer validator helper
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


@extend_schema(responses={200: LoginResponseSerializer}, auth=[])
class AdminLoginView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = AppAdminLoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        user = User.objects.filter(phone_number=vd["phone_number"]).first()
        if not user:
            return Response(
                {"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )

        app_admin: AppAdmin = getattr(user, "app_admin", None)
        if not app_admin:
            return Response(
                {"error": "Not an app admin account"}, status=status.HTTP_403_FORBIDDEN
            )
        if not user or not user.check_password(vd["password"]):
            return Response(
                {"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )

        token = issue_jwt_for_user(user)
        return Response(
            {
                "message": "Logged in successfully",
                "access": token["access"],
                "refresh": token["refresh"],
            }
        )


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


# class AdminReferralPayoutListView(BaseAppAdminAPIView, ListAPIView):
#     serializer_class = ReferralPayoutSerializer

#     def get_queryset(self):
#         qs = (
#             ReferralPayout.objects
#             .select_related("user")
#             .order_by("-created_at")
#         )

#         user_id = self.request.query_params.get("user_id")
#         if user_id:
#             qs = qs.filter(user_id=user_id)

#         return qs

#     def list(self, request, *args, **kwargs):
#         qs = self.get_queryset()

#         total_units = qs.aggregate(
#             total=Sum("units_paid")
#         )["total"] or 0

#         total_payouts = qs.count()

#         serializer = self.get_serializer(qs, many=True)

#         return Response({
#             "count": total_payouts,
#             "total_units_paid": total_units,
#             "results": serializer.data,
#         })


class AdminReferralPayoutListView(BaseAppAdminAPIView, ListAPIView):
    serializer_class = ReferralPayoutSerializer

    def get_queryset(self):
        qs = ReferralPayout.objects.select_related("user").order_by("-created_at")

        user_id = self.request.query_params.get("user_id")
        if user_id:
            qs = qs.filter(user_id=user_id)

        return qs

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()

        # 🔥 global stats (not paginated)
        total_units = qs.aggregate(total=Sum("units_paid"))["total"] or 0

        # 🔥 paginate properly
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)

            # 🔥 inject extra metadata
            response.data["total_units_paid"] = total_units
            return response

        # fallback (no pagination)
        serializer = self.get_serializer(qs, many=True)
        return Response(
            {
                "results": serializer.data,
                "total_units_paid": total_units,
            }
        )


class AdminReferralPayoutDetailView(BaseAppAdminAPIView, RetrieveAPIView):
    queryset = ReferralPayout.objects.all()
    serializer_class = ReferralPayoutSerializer

    def retrieve(self, request, *args, **kwargs):
        payout = self.get_object()

        return Response(
            {
                "id": payout.id,
                "user_id": payout.user_id,
                "units_paid": payout.units_paid,
                "referrals_used": payout.referrals_used,
                "created_at": payout.created_at,
                # 🔥 include snapshot here
                "referrals": payout.referral_snapshot,
                "is_valid": verify_snapshot_integrity(payout),
            }
        )


class _AppAdminRoleGuardMixin:
    """
    Simple role-gate for sensitive admin actions (finance ops).
    """

    allowed_roles: set[str] = set()

    def _require_app_admin_roles(self, request, roles: set[str]):
        try:
            app_admin = request.user.app_admin
        except Exception:
            raise PermissionDenied("App admin profile not found")
        if app_admin.role not in roles:
            raise PermissionDenied("Insufficient privileges for this action")


class AdminDashboardStatsView(BaseAppAdminAPIView):
    def get(self, request):
        # --- USERS ---
        user_stats = User.objects.aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(is_active=True)),
            inactive=Count("id", filter=Q(is_active=False)),
        )

        # --- EMPLOYEES ---
        total_drivers = DriverProfile.objects.count()
        total_businesses = Business.objects.count()

        # --- WITHDRAWALS ---
        pending_withdrawals_qs = Withdrawal.objects.filter(
            status__in=["pending_batch", "processing"]
        )

        pending_withdrawals = pending_withdrawals_qs.count()
        pending_withdrawals_amount = pending_withdrawals_qs.aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0")

        # --- DRIVERS ---
        pending_driver_submissions = DriverOnboardingSubmission.objects.filter(
            status=DriverOnboardingSubmission.STATUS_SUBMITTED
        ).count()

        pending_driver_documents = DriverDocument.objects.filter(
            status=DriverDocument.STATUS_PENDING
        ).count()

        # --- REFERRALS ---
        referral_eligible_users = (
            User.objects.annotate(
                unpaid=Count(
                    "profile_referrals_made",
                    filter=Q(
                        profile_referrals_made__converted_at__isnull=False,
                        profile_referrals_made__is_consumed=False,
                    ),
                )
            )
            .filter(unpaid__gte=REFERRALS_PER_UNIT)
            .count()
        )

        return Response(
            {
                "users": {
                    "total": user_stats["total"],
                    "active": user_stats["active"],
                    "inactive": user_stats["inactive"],
                },
                "employees": {
                    "drivers": total_drivers,
                    "businesses": total_businesses,
                },
                "withdrawals": {
                    "pending_or_processing_count": pending_withdrawals,
                    "pending_or_processing_amount_kobo": pending_withdrawals_amount,
                    "pending_or_processing_amount_ngn": pending_withdrawals_amount
                    / Decimal("100"),
                },
                "drivers": {
                    "pending_onboarding_submissions": pending_driver_submissions,
                    "pending_documents": pending_driver_documents,
                },
                "referrals": {
                    "eligible_users_for_payout": referral_eligible_users,
                },
            }
        )


class AdminUserListView(BaseAppAdminAPIView, ListAPIView):
    serializer_class = AdminUserListSerializer

    def get_queryset(self):
        qs = User.objects.all().order_by("-id")

        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(email__icontains=q)
                | Q(name__icontains=q)
                | Q(phone_number__icontains=q)
            )

        role = (self.request.query_params.get("role") or "").strip().lower()
        if role == "drivers":
            qs = qs.filter(profile_bases__profile_type="driver")
        elif role == "customers":
            qs = qs.filter(profile_bases__profile_type="customer")
        elif role == "business_admins":
            qs = qs.filter(business_admin__isnull=False)
        elif role == "app_admins":
            qs = qs.filter(app_admin__isnull=False)

        return qs.distinct()


class AdminUserDetailView(BaseAppAdminAPIView):
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
        # Optional details (avoid crashing if not present)
        if getattr(user, "driver_profile", None):
            payload["driver_profile"] = AdminDriverListSerializer(
                user.driver_profile
            ).data
        if getattr(user, "business_admin", None) and getattr(
            user.business_admin, "business", None
        ):
            payload["business"] = AdminBusinessListSerializer(
                user.business_admin.business
            ).data

        return Response(payload)


class AdminDriverListView(BaseAppAdminAPIView, ListAPIView):
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
        elif status_filter == "available":
            qs = qs.filter(is_available=True)

        return qs


class AdminDriverOnboardingReviewView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """
    Approve/reject the most recent submitted onboarding submission for a driver.
    """

    allowed_roles = {
        AppAdmin.Role.SUPPORT,
        AppAdmin.Role.SUPERVISOR,
        AppAdmin.Role.ADMIN,
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


class AdminBusinessListView(BaseAppAdminAPIView, ListAPIView):
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


class AdminBusinessUpdateView(
    BaseAppAdminAPIView, _AppAdminRoleGuardMixin
):  # use like completed review
    allowed_roles = {AppAdmin.Role.SUPERVISOR, AppAdmin.Role.ADMIN}
    serializer_class = AdminBusinessUpdateSerializer

    def patch(self, request, business_id: int):
        self._require_app_admin_roles(request, self.allowed_roles)

        business = Business.objects.filter(id=business_id).first()
        if not business:
            raise NotFound("Business not found")

        vd = self.validate_serializer()

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


class AdminWithdrawalListView(BaseAppAdminAPIView, ListAPIView):
    serializer_class = AdminWithdrawalSerializer

    def get_queryset(self):
        qs = Withdrawal.objects.select_related("user", "ledger_entry").order_by(
            "-requested_at"
        )

        status_q = (self.request.query_params.get("status") or "").strip().lower()
        if status_q:
            qs = qs.filter(status=status_q)

        strategy = (self.request.query_params.get("strategy") or "").strip().lower()
        if strategy:
            qs = qs.filter(strategy=strategy)

        user_id = (self.request.query_params.get("user_id") or "").strip()
        if user_id.isdigit():
            qs = qs.filter(user_id=int(user_id))

        from_dt = self.request.query_params.get("from")
        to_dt = self.request.query_params.get("to")
        # ISO datetimes expected, e.g. 2026-04-19T00:00:00Z
        if from_dt:
            try:
                qs = qs.filter(requested_at__gte=from_dt)
            except Exception:
                pass
        if to_dt:
            try:
                qs = qs.filter(requested_at__lte=to_dt)
            except Exception:
                pass

        return qs


class AdminWithdrawalDetailView(BaseAppAdminAPIView, RetrieveAPIView):
    queryset = Withdrawal.objects.select_related("user", "ledger_entry")
    serializer_class = AdminWithdrawalSerializer
    lookup_url_kwarg = "withdrawal_id"


class AdminWithdrawalRetryView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    allowed_roles = {
        AppAdmin.Role.FINANCE,
        AppAdmin.Role.SUPERVISOR,
        AppAdmin.Role.ADMIN,
    }

    def post(self, request, withdrawal_id):
        self._require_app_admin_roles(request, self.allowed_roles)

        withdrawal = Withdrawal.objects.filter(id=withdrawal_id).first()
        if not withdrawal:
            raise NotFound("Withdrawal not found")

        execute_realtime_withdrawal.delay(str(withdrawal.id))
        return Response(
            {"detail": "Withdrawal retry queued", "withdrawal_id": str(withdrawal.id)}
        )


class AdminWithdrawalMarkPaidView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    allowed_roles = {
        AppAdmin.Role.FINANCE,
        AppAdmin.Role.SUPERVISOR,
        AppAdmin.Role.ADMIN,
    }

    def post(self, request, withdrawal_id):
        self._require_app_admin_roles(request, self.allowed_roles)

        withdrawal = (
            Withdrawal.objects.filter(id=withdrawal_id).select_related("user").first()
        )
        if not withdrawal:
            raise NotFound("Withdrawal not found")

        mark_withdrawal_paid(withdrawal)
        return Response(
            {
                "detail": "Withdrawal marked as complete",
                "withdrawal_id": str(withdrawal.id),
                "status": withdrawal.status,
            }
        )


class AdminWithdrawalMarkFailedView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    allowed_roles = {
        AppAdmin.Role.FINANCE,
        AppAdmin.Role.SUPERVISOR,
        AppAdmin.Role.ADMIN,
    }
    serializer_class = AdminWithdrawalMarkFailedSerializer

    def post(self, request, withdrawal_id):
        self._require_app_admin_roles(request, self.allowed_roles)

        withdrawal = (
            Withdrawal.objects.filter(id=withdrawal_id)
            .select_related("user", "ledger_entry")
            .first()
        )
        if not withdrawal:
            raise NotFound("Withdrawal not found")

        vd = self.validate_serializer()
        mark_withdrawal_failed(withdrawal, vd["reason"])
        return Response(
            {
                "detail": "Withdrawal marked as failed",
                "withdrawal_id": str(withdrawal.id),
                "status": withdrawal.status,
            }
        )


class AdminWithdrawalBatchExecuteView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    allowed_roles = {AppAdmin.Role.FINANCE, AppAdmin.Role.ADMIN}

    def post(self, request):
        self._require_app_admin_roles(request, self.allowed_roles)
        execute_batch_payouts.delay()
        return Response({"detail": "Batch payouts execution queued"})


class AdminWithdrawalReconcileView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    allowed_roles = {AppAdmin.Role.FINANCE, AppAdmin.Role.ADMIN}

    def post(self, request):
        self._require_app_admin_roles(request, self.allowed_roles)
        reconcile_stale_processing_withdrawals.delay()
        retry_pending_withdrawals.delay()
        return Response({"detail": "Reconciliation + retry queued"})


class AdminNotificationListView(BaseAppAdminAPIView, ListAPIView):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = Notification.objects.select_related("user").order_by("-created_at")

        user_id = (self.request.query_params.get("user_id") or "").strip()
        if user_id.isdigit():
            qs = qs.filter(user_id=int(user_id))

        is_read = (self.request.query_params.get("is_read") or "").strip().lower()
        if is_read in {"true", "false"}:
            qs = qs.filter(is_read=(is_read == "true"))

        ntype = (self.request.query_params.get("type") or "").strip().lower()
        if ntype:
            qs = qs.filter(notification_type=ntype)

        return qs


class AdminSendNotificationView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    allowed_roles = {
        AppAdmin.Role.SUPPORT,
        AppAdmin.Role.SUPERVISOR,
        AppAdmin.Role.FINANCE,
        AppAdmin.Role.ADMIN,
    }
    serializer_class = AdminSendNotificationSerializer

    def post(self, request):
        self._require_app_admin_roles(request, self.allowed_roles)
        vd = self.validate_serializer()

        notification_type = (
            vd.get("notification_type") or Notification.TYPE_SYSTEM
        ).strip() or Notification.TYPE_SYSTEM
        title = vd["title"]
        body = vd["body"]
        payload = vd.get("payload_json") or {}

        if vd.get("user_id"):
            user = User.objects.filter(id=vd["user_id"]).first()
            if not user:
                raise NotFound("User not found")
            notif = create_notification(
                user=user,
                title=title,
                body=body,
                notification_type=notification_type,
                payload=payload,
            )
            return Response(
                {
                    "detail": "Notification sent",
                    "notification": NotificationSerializer(notif).data,
                }
            )

        audience = vd.get("audience")
        users_qs = User.objects.filter(is_active=True)
        if audience == "customers":
            users_qs = users_qs.filter(profile_bases__profile_type="customer")
        elif audience == "drivers":
            users_qs = users_qs.filter(profile_bases__profile_type="driver")
        elif audience == "business_admins":
            users_qs = users_qs.filter(business_admin__isnull=False)

        users_qs = users_qs.distinct()
        created = create_bulk_notifications(
            users=list(users_qs),
            title=title,
            body=body,
            notification_type=notification_type,
            payload=payload,
        )

        return Response(
            {
                "detail": "Broadcast queued",
                "audience": audience,
                "created": len(created),
            }
        )
