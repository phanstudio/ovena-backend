from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema  # type: ignore

from accounts.models import DriverProfile
from authflow.authentication import CustomDriverAuth
from authflow.permissions import IsDriver
from driver_api.models import SupportTicket, SupportTicketMessage
from support_center.serializers import (
    FAQItemSerializer,
    TicketCreateSerializer,
    TicketDetailSerializer,
    TicketListSerializer,
    TicketMessageCreateSerializer,
    TicketMessageSerializer,
)
from support_center.services import get_active_faq_queryset


class DriverSupportPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100


class BaseDriverSupportAPIView(APIView):
    authentication_classes = [CustomDriverAuth]
    permission_classes = [IsDriver]

    def get_driver(self, request) -> DriverProfile:
        profile = request.user.driver_profile
        if not profile:
            profile = get_object_or_404(DriverProfile, user=request.user)
        return profile


class DriverFAQListView(BaseDriverSupportAPIView):
    def get(self, request):
        qs = get_active_faq_queryset()
        return Response({"detail": "FAQ list", "data": FAQItemSerializer(qs, many=True).data})


class SupportTicketListCreateView(BaseDriverSupportAPIView):
    pagination_class = DriverSupportPagination

    @extend_schema(responses=TicketListSerializer)
    def get(self, request):
        driver = self.get_driver(request)
        qs = SupportTicket.objects.filter(driver=driver).order_by("-created_at")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        ser = TicketListSerializer(page, many=True)
        return paginator.get_paginated_response({"detail": "Support tickets", "data": ser.data})

    @extend_schema(request=TicketCreateSerializer, responses=TicketDetailSerializer)
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


class SupportTicketDetailView(BaseDriverSupportAPIView):
    def get(self, request, ticket_id: int):
        driver = self.get_driver(request)
        ticket = get_object_or_404(SupportTicket, id=ticket_id, driver=driver)
        return Response({"detail": "Support ticket detail", "data": TicketDetailSerializer(ticket).data})


class SupportTicketMessageListCreateView(BaseDriverSupportAPIView):
    pagination_class = DriverSupportPagination

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

