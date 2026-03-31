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
from rest_framework.viewsets import GenericViewSet
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin, CreateModelMixin, RetrieveModelMixin


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

class BaseSupportTicketViewSet(
    ListModelMixin,
    CreateModelMixin,
    RetrieveModelMixin,
    GenericViewSet
):

    pagination_class = SupportPagination

    owner_role = None
    sender_role = None

    list_serializer = None
    detail_serializer = None
    create_serializer = None
    message_serializer = None
    message_create_serializer = None

    def get_queryset(self):
        return SupportTicket.objects.filter(
            owner=self.request.user,
            owner_role=self.owner_role.value
        ).order_by("-created_at")

    def get_serializer_class(self):

        if self.action == "list":
            return self.list_serializer

        if self.action == "retrieve":
            return self.detail_serializer

        if self.action == "create":
            return self.create_serializer

        return self.detail_serializer

    @extend_schema(
        request=TicketCreateSerializer,
        responses=TicketDetailSerializer
    )
    def create(self, request, *args, **kwargs):

        serializer = self.create_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ticket = create_support_ticket(
            user=request.user,
            role=self.owner_role,
            subject=serializer.validated_data["subject"],
            message=serializer.validated_data["description"],
            category=serializer.validated_data.get("category", "general"),
            priority=serializer.validated_data.get("priority"),
            description=serializer.validated_data["description"],
        )

        return Response(
            {
                "detail": "Support ticket created",
                "data": self.detail_serializer(ticket).data
            },
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):

        ticket = self.get_object()

        if request.method == "GET":

            qs = SupportTicketMessage.objects.filter(ticket=ticket)

            paginator = self.pagination_class()
            page = paginator.paginate_queryset(qs, request)

            return paginator.get_paginated_response({
                "detail": "Ticket messages",
                "data": self.message_serializer(page, many=True).data
            })

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

class DriverSupportTicketViewSet(
    BaseDriverSupportAPIView,
    BaseSupportTicketViewSet
):

    owner_role = Role.OWNER_DRIVER
    sender_role = Role.OWNER_DRIVER

    list_serializer = TicketListSerializer
    detail_serializer = TicketDetailSerializer
    create_serializer = TicketCreateSerializer
    message_serializer = TicketMessageSerializer
    message_create_serializer = TicketMessageCreateSerializer

    @extend_schema(methods=["GET"], responses=TicketMessageSerializer(many=True))
    @extend_schema(methods=["POST"], request=TicketMessageCreateSerializer, responses=TicketMessageSerializer)
    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        return super().messages(request, pk=pk)

class BusinessSupportTicketViewSet(
    BaseBusinessSupportAPIView,
    BaseSupportTicketViewSet
):

    owner_role = Role.OWNER_BUSINESS_ADMIN
    sender_role = Role.OWNER_BUSINESS_ADMIN

    list_serializer = BusinessTicketListSerializer
    detail_serializer = BusinessTicketDetailSerializer
    create_serializer = BusinessTicketCreateSerializer
    message_serializer = BusinessTicketMessageSerializer
    message_create_serializer = BusinessTicketMessageCreateSerializer

    @extend_schema(methods=["GET"], responses=BusinessTicketMessageSerializer(many=True))
    @extend_schema(methods=["POST"], request=BusinessTicketMessageCreateSerializer, responses=BusinessTicketMessageSerializer)
    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        return super().messages(request, pk=pk)

# we need system views
# we need customer views
# we need support views
