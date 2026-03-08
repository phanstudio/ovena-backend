import hashlib
import hmac
import json

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import DriverAvailability, DriverProfile
from authflow.authentication import CustomDriverAuth
from authflow.permissions import IsDriver
from driver_api.models import (
    DriverLedgerEntry,
    DriverNotification,
    DriverWithdrawalRequest,
    SupportFAQItem,
    SupportTicket,
    SupportTicketMessage,
)
from driver_api.serializers import (
    AnalysisPerformanceQuerySerializer,
    DriverAvailabilityUpdateSerializer,
    DriverDashboardSerializer,
    DriverNotificationSerializer,
    DriverProfileSerializer,
    EarningsSummarySerializer,
    FAQItemSerializer,
    LedgerEntrySerializer,
    TicketCreateSerializer,
    TicketDetailSerializer,
    TicketListSerializer,
    TicketMessageCreateSerializer,
    TicketMessageSerializer,
    WithdrawalEligibilitySerializer,
    WithdrawalRequestCreateSerializer,
    WithdrawalRequestSerializer,
    mark_notifications_read,
)
from driver_api.services import (
    create_withdrawal_request,
    earnings_summary,
    evaluate_withdrawal_eligibility,
    parse_range,
    performance_metrics,
    sync_wallet_from_ledger,
)
from driver_api.tasks import process_withdrawal, reconcile_paystack_webhook


class BaseDriverAPIView(APIView):
    authentication_classes = [CustomDriverAuth]
    permission_classes = [IsDriver]

    def get_driver(self, request) -> DriverProfile:
        profile = getattr(request.user, "driver_profile", None)
        if not profile:
            profile = get_object_or_404(DriverProfile, user=request.user)
        return profile


class DriverLimitOffsetPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100


class DriverDashboardView(BaseDriverAPIView):
    @extend_schema(responses=DriverDashboardSerializer)
    def get(self, request):
        driver = self.get_driver(request)
        wallet = sync_wallet_from_ledger(driver)
        active_order = None
        if driver.current_order_id:
            order = driver.current_order
            active_order = {
                "id": order.id,
                "order_number": order.order_number,
                "status": order.status,
                "created_at": order.created_at,
            }
        payload = {
            "profile": {
                "id": driver.id,
                "first_name": driver.first_name,
                "last_name": driver.last_name,
                "rating": driver.avg_rating,
                "total_deliveries": driver.total_deliveries,
                "is_online": driver.is_online,
                "is_available": driver.is_available,
            },
            "wallet": {
                "current_balance": wallet.current_balance,
                "available_balance": wallet.available_balance,
                "pending_balance": wallet.pending_balance,
            },
            "active_order": active_order,
            "unread_notifications": DriverNotification.objects.filter(driver=driver, is_read=False).count(),
            "open_tickets": SupportTicket.objects.filter(
                driver=driver,
                status__in=[SupportTicket.STATUS_OPEN, SupportTicket.STATUS_IN_PROGRESS],
            ).count(),
        }
        return Response({"detail": "Driver dashboard loaded", "data": payload})


class DriverProfileView(BaseDriverAPIView):
    @extend_schema(responses=DriverProfileSerializer)
    def get(self, request):
        driver = self.get_driver(request)
        payload = {
            "first_name": driver.first_name,
            "last_name": driver.last_name,
            "gender": driver.gender,
            "birth_date": driver.birth_date,
            "residential_address": driver.residential_address,
            "phone_number": request.user.phone_number or "",
            "email": request.user.email or "",
            "vehicle_make": driver.vehicle_make or "",
            "vehicle_type": driver.vehicle_type or "",
            "vehicle_number": driver.vehicle_number or "",
        }
        return Response({"detail": "Driver profile fetched", "data": payload})

    @extend_schema(request=DriverProfileSerializer, responses=DriverProfileSerializer)
    def patch(self, request):
        driver = self.get_driver(request)
        serializer = DriverProfileSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        user_updates = []
        for field in ["phone_number", "email"]:
            if field in vd:
                setattr(request.user, field, vd[field])
                user_updates.append(field)
        if user_updates:
            request.user.save(update_fields=user_updates)

        driver_updates = []
        for field in [
            "first_name",
            "last_name",
            "gender",
            "birth_date",
            "residential_address",
            "vehicle_make",
            "vehicle_type",
            "vehicle_number",
        ]:
            if field in vd:
                setattr(driver, field, vd[field])
                driver_updates.append(field)
        if driver_updates:
            driver.save(update_fields=driver_updates)

        return self.get(request)


class DriverAvailabilityView(BaseDriverAPIView):
    @extend_schema(request=DriverAvailabilityUpdateSerializer)
    def put(self, request):
        driver = self.get_driver(request)
        serializer = DriverAvailabilityUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        updates = []
        if "is_online" in vd:
            driver.is_online = vd["is_online"]
            updates.append("is_online")
        if "is_available" in vd:
            driver.is_available = vd["is_available"]
            updates.append("is_available")
        if updates:
            driver.last_location_update = timezone.now()
            updates.append("last_location_update")
            driver.save(update_fields=updates)

        if "schedule" in vd:
            DriverAvailability.objects.filter(driver=driver).delete()
            DriverAvailability.objects.bulk_create(
                [DriverAvailability(driver=driver, weekday=s["weekday"], time_mask=s["time_mask"]) for s in vd["schedule"]]
            )

        schedule = DriverAvailability.objects.filter(driver=driver).order_by("weekday")
        return Response(
            {
                "detail": "Availability updated",
                "data": {
                    "is_online": driver.is_online,
                    "is_available": driver.is_available,
                    "schedule": [{"weekday": s.weekday, "time_mask": s.time_mask} for s in schedule],
                },
            }
        )


class DriverFAQListView(BaseDriverAPIView):
    def get(self, request):
        qs = SupportFAQItem.objects.filter(is_active=True, category__is_active=True).select_related("category")
        return Response({"detail": "FAQ list", "data": FAQItemSerializer(qs, many=True).data})


class SupportTicketListCreateView(BaseDriverAPIView):
    pagination_class = DriverLimitOffsetPagination

    def get(self, request):
        driver = self.get_driver(request)
        qs = SupportTicket.objects.filter(driver=driver).order_by("-created_at")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        ser = TicketListSerializer(page, many=True)
        return paginator.get_paginated_response({"detail": "Support tickets", "data": ser.data})

    def post(self, request):
        driver = self.get_driver(request)
        serializer = TicketCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = serializer.save(driver=driver)
        SupportTicketMessage.objects.create(
            ticket=ticket,
            sender_type=SupportTicketMessage.SENDER_DRIVER,
            sender_id=request.user.id,
            message=ticket.description,
        )
        return Response(
            {"detail": "Support ticket created", "data": TicketDetailSerializer(ticket).data},
            status=status.HTTP_201_CREATED,
        )


class SupportTicketDetailView(BaseDriverAPIView):
    def get(self, request, ticket_id: int):
        driver = self.get_driver(request)
        ticket = get_object_or_404(SupportTicket, id=ticket_id, driver=driver)
        return Response({"detail": "Support ticket detail", "data": TicketDetailSerializer(ticket).data})


class SupportTicketMessageListCreateView(BaseDriverAPIView):
    pagination_class = DriverLimitOffsetPagination

    def _ticket(self, request, ticket_id):
        driver = self.get_driver(request)
        return get_object_or_404(SupportTicket, id=ticket_id, driver=driver)

    def get(self, request, ticket_id: int):
        ticket = self._ticket(request, ticket_id)
        qs = SupportTicketMessage.objects.filter(ticket=ticket).order_by("created_at")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            {"detail": "Ticket messages", "data": TicketMessageSerializer(page, many=True).data}
        )

    def post(self, request, ticket_id: int):
        ticket = self._ticket(request, ticket_id)
        if ticket.status == SupportTicket.STATUS_CLOSED:
            return Response({"detail": "Ticket is closed"}, status=status.HTTP_400_BAD_REQUEST)
        serializer = TicketMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        msg = SupportTicketMessage.objects.create(
            ticket=ticket,
            sender_type=SupportTicketMessage.SENDER_DRIVER,
            sender_id=request.user.id,
            message=serializer.validated_data["message"],
            attachments_json=serializer.validated_data.get("attachments_json", []),
        )
        return Response({"detail": "Message sent", "data": TicketMessageSerializer(msg).data}, status=status.HTTP_201_CREATED)


class DriverNotificationListView(BaseDriverAPIView):
    pagination_class = DriverLimitOffsetPagination

    def get(self, request):
        driver = self.get_driver(request)
        qs = DriverNotification.objects.filter(driver=driver).order_by("-created_at")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            {"detail": "Notifications", "data": DriverNotificationSerializer(page, many=True).data}
        )


class DriverNotificationUnreadCountView(BaseDriverAPIView):
    def get(self, request):
        driver = self.get_driver(request)
        count = DriverNotification.objects.filter(driver=driver, is_read=False).count()
        return Response({"detail": "Unread notification count", "data": {"unread_count": count}})


class DriverNotificationMarkReadView(BaseDriverAPIView):
    def post(self, request, notification_id: int):
        driver = self.get_driver(request)
        notification = get_object_or_404(DriverNotification, id=notification_id, driver=driver)
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at"])
        return Response({"detail": "Notification marked as read"})


class DriverNotificationReadAllView(BaseDriverAPIView):
    def post(self, request):
        driver = self.get_driver(request)
        count = mark_notifications_read(DriverNotification.objects.filter(driver=driver))
        return Response({"detail": "All notifications marked as read", "data": {"updated": count}})


class DriverEarningsSummaryView(BaseDriverAPIView):
    def get(self, request):
        driver = self.get_driver(request)
        range_key = request.query_params.get("range", "30d")
        start, end = parse_range(range_key)
        data = earnings_summary(driver=driver, start=start, end=end)
        return Response({"detail": "Earnings summary", "data": EarningsSummarySerializer(data).data})


class DriverEarningsHistoryView(BaseDriverAPIView):
    pagination_class = DriverLimitOffsetPagination

    def get(self, request):
        driver = self.get_driver(request)
        qs = DriverLedgerEntry.objects.filter(driver=driver).order_by("-created_at")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response({"detail": "Earnings history", "data": LedgerEntrySerializer(page, many=True).data})


class DriverWithdrawEligibilityView(BaseDriverAPIView):
    def get(self, request):
        driver = self.get_driver(request)
        decision = evaluate_withdrawal_eligibility(driver=driver)
        payload = {
            "eligible": decision.eligible,
            "minimum_amount": decision.minimum_amount,
            "max_amount": decision.max_amount,
            "available_balance": decision.available_balance,
            "checks": decision.checks,
        }
        return Response({"detail": "Withdrawal eligibility", "data": WithdrawalEligibilitySerializer(payload).data})


class DriverWithdrawListCreateView(BaseDriverAPIView):
    pagination_class = DriverLimitOffsetPagination

    def get(self, request):
        driver = self.get_driver(request)
        qs = DriverWithdrawalRequest.objects.filter(driver=driver).order_by("-created_at")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response({"detail": "Withdrawal requests", "data": WithdrawalRequestSerializer(page, many=True).data})

    @transaction.atomic
    def post(self, request):
        driver = self.get_driver(request)
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response({"detail": "Idempotency-Key header is required"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = WithdrawalRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        withdrawal, created = create_withdrawal_request(
            driver=driver,
            amount=serializer.validated_data["amount"],
            idempotency_key=idempotency_key,
        )
        if created and withdrawal.status == DriverWithdrawalRequest.STATUS_APPROVED:
            process_withdrawal.delay(withdrawal.id)

        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(
            {
                "detail": "Withdrawal request created" if created else "Duplicate request; existing withdrawal returned",
                "data": WithdrawalRequestSerializer(withdrawal).data,
            },
            status=status_code,
        )


class DriverWithdrawDetailView(BaseDriverAPIView):
    def get(self, request, withdrawal_id: int):
        driver = self.get_driver(request)
        withdrawal = get_object_or_404(DriverWithdrawalRequest, id=withdrawal_id, driver=driver)
        return Response({"detail": "Withdrawal detail", "data": WithdrawalRequestSerializer(withdrawal).data})


class DriverAnalysisPerformanceView(BaseDriverAPIView):
    def get(self, request):
        driver = self.get_driver(request)
        params = {
            "range": request.query_params.get("range", "30d"),
            "from_date": request.query_params.get("from"),
            "to_date": request.query_params.get("to"),
            "granularity": request.query_params.get("granularity", "day"),
        }
        serializer = AnalysisPerformanceQuerySerializer(data=params)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        start, end = parse_range(
            vd["range"],
            from_date=vd.get("from_date"),
            to_date=vd.get("to_date"),
        )
        data = performance_metrics(
            driver=driver,
            start=start,
            end=end,
            granularity=vd.get("granularity", "day"),
        )
        return Response({"detail": "Performance analysis", "data": data})


class PaystackWithdrawalWebhookView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        signature = request.headers.get("x-paystack-signature")
        payload_bytes = request.body or b""
        secret = getattr(settings, "PAYSTACK_SECRET_KEY", "") or ""
        expected = hmac.new(
            key=secret.encode("utf-8"),
            msg=payload_bytes,
            digestmod=hashlib.sha512,
        ).hexdigest()
        if not signature or signature != expected:
            return Response({"detail": "Invalid webhook signature"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            body = json.loads(payload_bytes.decode("utf-8"))
        except Exception:
            return Response({"detail": "Invalid JSON"}, status=status.HTTP_400_BAD_REQUEST)

        event = body.get("event")
        data = body.get("data", {})
        if event != "transfer.success" and event != "transfer.failed":
            return Response({"detail": "Ignored event"}, status=status.HTTP_200_OK)

        transfer_reference = data.get("reference", "")
        transfer_status = data.get("status", "failed")
        reason = data.get("failure_reason", "")
        reconcile_paystack_webhook(
            transfer_reference=transfer_reference,
            transfer_status=transfer_status,
            reason=reason,
        )
        return Response({"detail": "Webhook processed"}, status=status.HTTP_200_OK)
