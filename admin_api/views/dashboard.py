from decimal import Decimal
from django.db.models import Sum, Count, Q
from django.utils import timezone
from rest_framework.response import Response

from accounts.models import User, DriverProfile, Business, Branch
from accounts.models.driver import DriverOnboardingSubmission, DriverDocument
from menu.models import Order
from menu.models.enums import OrderStatus
from payments.models import Withdrawal, Sale, LedgerEntry
from referrals.services import REFERRALS_PER_UNIT
from admin_api.models import AppAdmin
from .base import BaseAppAdminAPIView, _AppAdminRoleGuardMixin


class AdminDashboardStatsView(BaseAppAdminAPIView):
    """
    GET /api/admin/dashboard/stats/
    Comprehensive operational and real-time dashboard statistics.
    """

    def get(self, request):
        now = timezone.now()
        today = now.date()

        # --- USERS ---
        user_stats = User.objects.aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(is_active=True)),
            inactive=Count("id", filter=Q(is_active=False)),
        )

        # --- EMPLOYEES & REALTIME CAPACITY ---
        total_drivers = DriverProfile.objects.count()
        active_drivers = DriverProfile.objects.filter(is_online=True).count()
        busy_drivers = DriverProfile.objects.filter(is_online=True, is_available=False).count()
        available_drivers = DriverProfile.objects.filter(is_online=True, is_available=True).count()

        total_businesses = Business.objects.count()
        online_restaurants = Branch.objects.filter(is_active=True, is_accepting_orders=True).count()

        # --- ORDERS TODAY ---
        orders_today_qs = Order.objects.filter(created_at__date=today)
        total_orders_today = orders_today_qs.count()
        completed_orders_today = orders_today_qs.filter(status=OrderStatus.DELIVERED).count()

        revenue_today_agg = orders_today_qs.filter(
            status__in=[OrderStatus.DELIVERED, OrderStatus.CONFIRMED, OrderStatus.READY, OrderStatus.PICKED_UP, OrderStatus.ON_THE_WAY]
        ).aggregate(
            total_revenue=Sum("grand_total"),
            delivery_fees=Sum("delivery_price"),
            items_total=Sum("items_total"),
        )
        total_revenue_today = revenue_today_agg["total_revenue"] or Decimal("0")
        delivery_fees_today = revenue_today_agg["delivery_fees"] or Decimal("0")

        # Estimated commissions earned today
        commissions_today = orders_today_qs.filter(
            status=OrderStatus.DELIVERED
        ).aggregate(
            commissions=Sum("items_total")
        )["commissions"] or Decimal("0")
        commissions_earned_today = commissions_today * Decimal("0.10")

        # --- WITHDRAWALS ---
        pending_withdrawals_qs = Withdrawal.objects.filter(
            status__in=["pending_batch", "processing"]
        )
        pending_withdrawals = pending_withdrawals_qs.count()
        pending_withdrawals_amount = pending_withdrawals_qs.aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0")

        # --- DRIVER ONBOARDING ---
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
                "realtime": {
                    "active_riders": active_drivers,
                    "busy_riders": busy_drivers,
                    "available_riders": available_drivers,
                    "online_restaurants": online_restaurants,
                },
                "today": {
                    "total_orders": total_orders_today,
                    "completed_orders": completed_orders_today,
                    "total_revenue_ngn": total_revenue_today,
                    "delivery_fees_earned_ngn": delivery_fees_today,
                    "restaurant_commissions_earned_ngn": commissions_earned_today,
                },
                "withdrawals": {
                    "pending_or_processing_count": pending_withdrawals,
                    "pending_or_processing_amount_kobo": pending_withdrawals_amount,
                    "pending_or_processing_amount_ngn": pending_withdrawals_amount / Decimal("100"),
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


class AdminFinanceDashboardView(BaseAppAdminAPIView, _AppAdminRoleGuardMixin):
    """
    GET /api/admin/finance/dashboard/
    Financial overview: Revenue today, 7d, 30d, completed/pending payouts, wallet balances.
    """
    allowed_roles = {
        AppAdmin.Role.FINANCE,
        AppAdmin.Role.OPERATIONS,
        AppAdmin.Role.SUPERVISOR,
        AppAdmin.Role.ADMIN,
        AppAdmin.Role.OWNER,
        AppAdmin.Role.MANAGER,
    }

    def get(self, request):
        self._require_app_admin_roles(request, self.allowed_roles)
        now = timezone.now()
        today = now.date()
        week_ago = now - timezone.timedelta(days=7)
        month_ago = now - timezone.timedelta(days=30)

        # Sales aggregates (in kobo)
        revenue_today = Sale.objects.filter(
            status="completed", created_at__date=today
        ).aggregate(total=Sum("total_amount"))["total"] or 0

        revenue_weekly = Sale.objects.filter(
            status="completed", created_at__gte=week_ago
        ).aggregate(total=Sum("total_amount"))["total"] or 0

        revenue_monthly = Sale.objects.filter(
            status="completed", created_at__gte=month_ago
        ).aggregate(total=Sum("total_amount"))["total"] or 0

        # Withdrawals aggregates
        pending_payouts_qs = Withdrawal.objects.filter(status__in=["pending_batch", "processing"])
        completed_payouts_qs = Withdrawal.objects.filter(status="completed")

        pending_payouts = pending_payouts_qs.aggregate(
            count=Count("id"), total=Sum("amount")
        )
        completed_payouts = completed_payouts_qs.aggregate(
            count=Count("id"), total=Sum("amount")
        )

        # Platform commissions & delivery fees from Ledger
        platform_credit_agg = LedgerEntry.objects.filter(
            role="platform", type="credit"
        ).aggregate(total=Sum("amount"))["total"] or 0

        return Response({
            "revenue": {
                "today_ngn": Decimal(revenue_today) / Decimal("100"),
                "weekly_ngn": Decimal(revenue_weekly) / Decimal("100"),
                "monthly_ngn": Decimal(revenue_monthly) / Decimal("100"),
            },
            "payouts": {
                "pending_count": pending_payouts["count"] or 0,
                "pending_amount_ngn": Decimal(pending_payouts["total"] or 0) / Decimal("100"),
                "completed_count": completed_payouts["count"] or 0,
                "completed_amount_ngn": Decimal(completed_payouts["total"] or 0) / Decimal("100"),
            },
            "platform_earnings": {
                "total_platform_credit_ngn": Decimal(platform_credit_agg) / Decimal("100"),
            },
        })
