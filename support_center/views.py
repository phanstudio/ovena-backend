from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.generics import GenericAPIView
from drf_spectacular.utils import extend_schema  # type: ignore

from accounts.models import BusinessAdmin, DriverProfile
from authflow.authentication import CustomBAdminAuth, CustomDriverAuth
from authflow.permissions import IsBusinessAdmin, IsDriver
from support_center.models import SupportTicket, SupportTicketMessage
from support_center.serializers import (
    BusinessTicketCreateSerializer,
    BusinessTicketDetailSerializer,
    BusinessTicketListSerializer,
    BusinessTicketMessageCreateSerializer,
    BusinessTicketMessageSerializer,
    FAQItemSerializer,
    TicketCreateSerializer,
    TicketDetailSerializer,
    TicketListSerializer,
    TicketMessageCreateSerializer,
    TicketMessageSerializer,
)
from support_center.services import (
    get_active_faq_queryset, create_support_ticket, 
    create_support_ticket_message, Role
)


class SupportPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100

# base views
class BaseDriverSupportAPIView(GenericAPIView):
    authentication_classes = [CustomDriverAuth]
    permission_classes = [IsDriver]

    def get_driver(self, request) -> DriverProfile:
        profile = request.user.driver_profile
        if not profile:
            profile = get_object_or_404(DriverProfile, user=request.user)
        return profile

class BaseBusinessSupportAPIView(GenericAPIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def get_business_admin(self, request) -> BusinessAdmin:
        try:
            return request.user.business_admin
        except BusinessAdmin.DoesNotExist:
            return get_object_or_404(BusinessAdmin, user=request.user)

# views
class DriverFAQListView(BaseDriverSupportAPIView):
    def get(self, request):
        qs = get_active_faq_queryset()
        return Response({"detail": "FAQ list", "data": FAQItemSerializer(qs, many=True).data})

class BaseSupportTicketAPIView(GenericAPIView):

    pagination_class = SupportPagination

    list_serializer = None
    detail_serializer = None
    create_serializer = None
    message_serializer = None
    message_create_serializer = None

    owner_role = None # can change the role from str to the role object?
    sender_role = None

    def get_queryset(self, request):
        return SupportTicket.objects.filter(
            owner_role=self.owner_role,
            owner=request.user
        ).order_by("-created_at")

class SupportTicketListCreateView(BaseSupportTicketAPIView):

    @extend_schema(responses=TicketListSerializer)
    def get(self, request):
        qs = self.get_queryset(request)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)

        ser = self.list_serializer(page, many=True)

        return paginator.get_paginated_response({
            "detail": "Support tickets",
            "data": ser.data
        })

    @extend_schema(
        request=TicketCreateSerializer,
        responses=TicketDetailSerializer
    )
    def post(self, request):
        serializer = self.create_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ticket = create_support_ticket(
            user=request.user,
            role=self.owner_role,
            subject=serializer.validated_data["subject"],
            message=serializer.validated_data["description"],
            category=serializer.validated_data.get("category", "general"),
            priority=serializer.validated_data.get("priority"),
        )

        return Response(
            {
                "detail": "Support ticket created",
                "data": self.detail_serializer(ticket).data
            },
            status=status.HTTP_201_CREATED
        )

class SupportTicketDetailView(BaseSupportTicketAPIView):
    def get_ticket(self, request, ticket_id):
        return get_object_or_404(
            SupportTicket,
            id=ticket_id,
            owner_role=self.owner_role,
            owner=request.user
        )

    @extend_schema(responses=TicketDetailSerializer)
    def get(self, request, ticket_id):
        ticket = self.get_ticket(request, ticket_id)
        return Response({
            "detail": "Support ticket detail",
            "data": self.detail_serializer(ticket).data
        })

class SupportTicketMessageListCreateView(BaseSupportTicketAPIView):

    def get_ticket(self, request, ticket_id):
        return get_object_or_404(
            SupportTicket,
            id=ticket_id,
            owner_role=self.owner_role,
            owner=request.user
        )

    @extend_schema(responses=TicketMessageSerializer)
    def get(self, request, ticket_id):

        ticket = self.get_ticket(request, ticket_id)

        qs = SupportTicketMessage.objects.filter(ticket=ticket).order_by("created_at")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)

        return paginator.get_paginated_response({
            "detail": "Ticket messages",
            "data": self.message_serializer(page, many=True).data
        })

    @extend_schema(
        request=TicketMessageCreateSerializer,
        responses=TicketMessageSerializer
    )
    def post(self, request, ticket_id):

        ticket = self.get_ticket(request, ticket_id)

        if ticket.status == SupportTicket.STATUS_CLOSED:
            return Response(
                {"detail": "Ticket is closed"},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.message_create_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = create_support_ticket_message(
            role=self.sender_role,
            ticket=ticket,
            user=request.user,
            message=serializer.validated_data["message"],
            attachments_json=serializer.validated_data.get("attachments_json", [])
        )

        return Response(
            {
                "detail": "Message sent",
                "data": self.message_serializer(message).data
            },
            status=status.HTTP_201_CREATED
        )

class DriverSupportTicketListCreateView(
    BaseDriverSupportAPIView,
    SupportTicketListCreateView
):

    owner_role = Role.OWNER_DRIVER
    sender_role = Role.OWNER_DRIVER

    list_serializer = TicketListSerializer
    detail_serializer = TicketDetailSerializer
    create_serializer = TicketCreateSerializer
    message_serializer = TicketMessageSerializer
    message_create_serializer = TicketMessageCreateSerializer

class BusinessSupportTicketListCreateView(
    BaseBusinessSupportAPIView,
    SupportTicketListCreateView
):

    owner_role = Role.OWNER_BUSINESS_ADMIN
    sender_role = Role.OWNER_BUSINESS_ADMIN

    list_serializer = BusinessTicketListSerializer
    detail_serializer = BusinessTicketDetailSerializer
    create_serializer = BusinessTicketCreateSerializer
    message_serializer = BusinessTicketMessageSerializer
    message_create_serializer = BusinessTicketMessageCreateSerializer





# we need system views
# we need customer views
# we need support views
