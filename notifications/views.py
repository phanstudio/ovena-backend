from rest_framework.pagination import LimitOffsetPagination
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from notifications.serializers import NotificationSerializer
from notifications.services import (
    get_user_notifications_queryset,
    get_unread_count,
    get_notification_for_user,
    mark_notification_read,
    mark_all_notifications_read,
)

class NotificationPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100

class NotificationViewSet(
    GenericViewSet,
    ListModelMixin,
):
    permission_classes = [IsAuthenticated]
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
