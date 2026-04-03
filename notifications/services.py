from django.utils import timezone
from django.shortcuts import get_object_or_404

from notifications.models import Notification


def create_notification(
    *,
    user,
    title: str,
    body: str,
    notification_type: str = Notification.TYPE_GENERIC,
    payload: dict | None = None,
):
    return Notification.objects.create(
        user=user,
        title=title,
        body=body,
        notification_type=notification_type,
        payload_json=payload or {},
    )


def create_bulk_notifications(users, title, body, notification_type="generic", payload=None):
    notifications = [
        Notification(
            user=user,
            title=title,
            body=body,
            notification_type=notification_type,
            payload_json=payload or {},
        )
        for user in users
    ]

    return Notification.objects.bulk_create(notifications)


def get_user_notifications_queryset(user):
    return (
        Notification.objects
        .filter(user=user)
        .order_by("-created_at")
    )


def get_unread_count(user):
    return Notification.objects.filter(
        user=user,
        is_read=False
    ).count()


def get_notification_for_user(user, notification_id):
    return get_object_or_404(
        Notification,
        id=notification_id,
        user=user
    )


def mark_notification_read(notification: Notification):
    if notification.is_read:
        return notification

    notification.is_read = True
    notification.read_at = timezone.now()

    notification.save(update_fields=["is_read", "read_at"])

    return notification


def mark_all_notifications_read(user):
    now = timezone.now()

    return (
        Notification.objects
        .filter(user=user, is_read=False)
        .update(is_read=True, read_at=now)
    )