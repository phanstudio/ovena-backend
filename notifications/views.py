from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import LimitOffsetPagination

from accounts.models import DriverProfile
from authflow.authentication import CustomDriverAuth
from authflow.permissions import IsDriver
from driver_api.models import DriverNotification
from notifications.serializers import DriverNotificationSerializer
from notifications.services import get_driver_notifications_queryset, get_driver_unread_count, mark_notifications_read


class DriverNotificationPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100


class BaseDriverNotificationAPIView(APIView):
    authentication_classes = [CustomDriverAuth]
    permission_classes = [IsDriver]

    def get_driver(self, request) -> DriverProfile:
        profile = request.user.driver_profile
        if not profile:
            profile = get_object_or_404(DriverProfile, user=request.user)
        return profile


class DriverNotificationListView(BaseDriverNotificationAPIView):
    pagination_class = DriverNotificationPagination

    def get(self, request):
        driver = self.get_driver(request)
        qs = get_driver_notifications_queryset(driver)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            {"detail": "Notifications", "data": DriverNotificationSerializer(page, many=True).data}
        )


class DriverNotificationUnreadCountView(BaseDriverNotificationAPIView):
    def get(self, request):
        driver = self.get_driver(request)
        return Response({"detail": "Unread notification count", "data": {"unread_count": get_driver_unread_count(driver)}})


class DriverNotificationMarkReadView(BaseDriverNotificationAPIView):
    def post(self, request, notification_id: int):
        driver = self.get_driver(request)
        notification = get_object_or_404(DriverNotification, id=notification_id, driver=driver)
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at"])
        return Response({"detail": "Notification marked as read"})


class DriverNotificationReadAllView(BaseDriverNotificationAPIView):
    def post(self, request):
        driver = self.get_driver(request)
        count = mark_notifications_read(DriverNotification.objects.filter(driver=driver))
        return Response({"detail": "All notifications marked as read", "data": {"updated": count}})
