from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.exceptions import NotFound

from accounts.models import User
from notifications.models import Notification
from notifications.serializers import NotificationSerializer
from notifications.services import (
    notify_user,
    notify_users_bulk,
    resolve_notification_recipients,
)
from admin_api.models import AppAdmin
from admin_api.serializers import AdminSendNotificationSerializer
from .base import BaseAppAdminAPIView, _AppAdminRoleGuardMixin


class AdminNotificationListView(BaseAppAdminAPIView, ListAPIView):
    """
    GET /api/admin/notifications/
    List notifications with filters for user_id, is_read, and type.
    """
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
    """
    POST /api/admin/notifications/send/
    Send targeted or broadcast push/in-app notifications.
    """
    allowed_roles = {
        AppAdmin.Role.SUPPORT,
        AppAdmin.Role.SUPERVISOR,
        AppAdmin.Role.FINANCE,
        AppAdmin.Role.ADMIN,
        AppAdmin.Role.MARKETING,
        AppAdmin.Role.OPERATIONS,
        AppAdmin.Role.OWNER,
    }
    serializer_class = AdminSendNotificationSerializer

    def post(self, request):
        self._require_app_admin_roles(request, self.allowed_roles)
        vd = self.validate_serializer(request.data)

        notification_type = (
            vd.get("notification_type") or Notification.TYPE_SYSTEM
        ).strip() or Notification.TYPE_SYSTEM
        title = vd["title"]
        body = vd["body"]
        payload = vd.get("payload_json") or {}
        push = vd.get("push", True)

        if vd.get("user_id"):
            user = User.objects.filter(id=vd["user_id"]).first()
            if not user:
                raise NotFound("User not found")
            notif = notify_user(
                user=user,
                title=title,
                body=body,
                notification_type=notification_type,
                payload=payload,
                push=push,
            )
            return Response(
                {
                    "detail": "Notification sent",
                    "notification": NotificationSerializer(notif).data,
                }
            )

        resolved_audiences = vd.get("resolved_audiences") or []
        user_ids = vd.get("user_ids") or []
        users_qs = resolve_notification_recipients(
            audiences=resolved_audiences,
            user_ids=user_ids,
        )
        created = notify_users_bulk(
            users=list(users_qs),
            title=title,
            body=body,
            notification_type=notification_type,
            payload=payload,
            push=push,
        )

        audience_summary = (
            vd.get("audience")
            or (resolved_audiences[0] if len(resolved_audiences) == 1 else resolved_audiences)
        )

        return Response(
            {
                "detail": "Broadcast queued",
                "audience": audience_summary,
                "audiences": resolved_audiences,
                "created": len(created),
            }
        )
