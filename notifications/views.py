from rest_framework.pagination import LimitOffsetPagination
from rest_framework.viewsets import GenericViewSet
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import ListModelMixin
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from authflow.authentication import CustomDriverAuth, CustomBusinessAgentsAuth, CustomCustomerAuth
from authflow.permissions import IsDriver, IsBusinessAgent, IsCustomer, IsNotSuspended

from notifications.serializers import NotificationSerializer, BaseRegisterDeviceTokenSerialzer
from notifications.services import (
    get_user_notifications_queryset,
    get_unread_count,
    get_notification_for_user,
    mark_notification_read,
    mark_all_notifications_read,
)
from .models import DeviceToken


class NotificationPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100


class BaseNotificationViewSet(
    GenericViewSet,
    ListModelMixin,
):
    pagination_class = NotificationPagination
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return get_user_notifications_queryset(self.request.user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)

        return Response({
            "detail": "Notifications",
            "data": response.data
        })

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        return Response({
            "detail": "Unread notification count",
            "data": {
                "unread_count": get_unread_count(request.user)
            }
        })

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notification = get_notification_for_user(
            request.user,
            pk
        )

        mark_notification_read(notification)

        return Response({
            "detail": "Notification marked as read"
        })

    @action(detail=False, methods=["post"])
    def read_all(self, request):

        count = mark_all_notifications_read(request.user)

        return Response({
            "detail": "All notifications marked as read",
            "data": {
                "updated": count
            }
        })


class NotificationViewSet(BaseNotificationViewSet):
    permission_classes = [IsAuthenticated]


class DriverNotificationViewSet(BaseNotificationViewSet):
    authentication_classes = [CustomDriverAuth]
    permission_classes = [IsDriver, IsNotSuspended]


class BuisnessNotificationViewSet(BaseNotificationViewSet):
    authentication_classes = [CustomBusinessAgentsAuth]
    permission_classes = [IsBusinessAgent]


class CustomerNotificationViewSet(BaseNotificationViewSet):
    authentication_classes = [CustomCustomerAuth]
    permission_classes = [IsCustomer]


class BaseRegisterDeviceTokenView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BaseRegisterDeviceTokenSerialzer

    def post(self, request):
        serializer = self.get_serializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        token = vd.get("token")
        platform = vd.get("platform")
        if not token:
            return Response({"error": "token required"}, status=400)

        DeviceToken.objects.update_or_create(
            token=token,
            defaults={"user": request.user, "platform": platform},
        )
        return Response({"status": "ok"})


class CustomerRegisterDeviceTokenView(BaseRegisterDeviceTokenView):
    authentication_classes = [CustomCustomerAuth]
    permission_classes = [IsCustomer]


class BusinessRegisterDeviceTokenView(BaseRegisterDeviceTokenView):
    authentication_classes = [CustomBusinessAgentsAuth]
    permission_classes = [IsBusinessAgent]


class DriverRegisterDeviceTokenView(BaseRegisterDeviceTokenView):
    authentication_classes = [CustomDriverAuth]
    permission_classes = [IsDriver, IsNotSuspended]