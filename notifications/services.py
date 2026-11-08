from django.db.models import Q
from django.utils import timezone
from django.shortcuts import get_object_or_404

from accounts.models import User
from notifications.models import Notification
from notifications.firebase_service import send_push_to_user, send_push_to_users

AUDIENCE_ALL = "all"
AUDIENCE_CUSTOMERS = "customers"
AUDIENCE_DRIVERS = "drivers"
AUDIENCE_BUSINESSES = "businesses"
AUDIENCE_BUSINESS_ADMINS = "business_admins"
AUDIENCE_BUSINESS_STAFF = "business_staff"
AUDIENCE_ADMINS = "admins"

VALID_AUDIENCES = (
    AUDIENCE_ALL,
    AUDIENCE_CUSTOMERS,
    AUDIENCE_DRIVERS,
    AUDIENCE_BUSINESSES,
    AUDIENCE_BUSINESS_ADMINS,
    AUDIENCE_BUSINESS_STAFF,
    AUDIENCE_ADMINS,
)


def resolve_notification_recipients(
    *,
    audiences: list[str] | set[str] | tuple[str, ...] | None = None,
    user_ids: list[int] | set[int] | tuple[int, ...] | None = None,
):
    """
    Resolve active, deduplicated User queryset for any combination of
    audience segments and/or explicit user_ids.
    """
    qs = User.objects.filter(is_active=True)
    audience_set = set(audiences or [])

    if AUDIENCE_ALL in audience_set:
        return qs.distinct()

    query = Q()
    has_filter = False

    if AUDIENCE_CUSTOMERS in audience_set:
        query |= Q(customer_profile__isnull=False)
        has_filter = True
    if AUDIENCE_DRIVERS in audience_set:
        query |= Q(driver_profile__isnull=False)
        has_filter = True
    if AUDIENCE_BUSINESSES in audience_set:
        query |= Q(business_admin__isnull=False) | Q(
            primary_agent__isnull=False, primary_agent__revoked=False
        )
        has_filter = True
    if AUDIENCE_BUSINESS_ADMINS in audience_set:
        query |= Q(business_admin__isnull=False)
        has_filter = True
    if AUDIENCE_BUSINESS_STAFF in audience_set:
        query |= Q(primary_agent__isnull=False, primary_agent__revoked=False)
        has_filter = True
    if AUDIENCE_ADMINS in audience_set:
        query |= Q(app_admin__isnull=False)
        has_filter = True
    if user_ids:
        query |= Q(id__in=list(user_ids))
        has_filter = True

    if not has_filter:
        return qs.none()

    return qs.filter(query).distinct()


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


def notify_user(
    *,
    user,
    title: str,
    body: str,
    notification_type: str = Notification.TYPE_GENERIC,
    payload: dict | None = None,
    push: bool = True,
):
    """
    Single entry point: creates the in-app Notification row (so it shows up
    in the notifications list / unread count, same as before) AND, if the
    user has any registered device tokens, sends a push through Firebase.

    Push failures never raise or roll back the DB notification — the
    in-app notification is the source of truth, the push is best-effort.
    """
    notification = create_notification(
        user=user,
        title=title,
        body=body,
        notification_type=notification_type,
        payload=payload,
    )

    if push:
        push_data = {
            "notification_id": str(notification.id),
            "notification_type": notification_type,
            **(payload or {}),
        }
        send_push_to_user(user, title, body, data=push_data)

    return notification


def notify_users_bulk(
    users,
    title,
    body,
    notification_type="generic",
    payload=None,
    push: bool = True,
):
    """
    Bulk variant of notify_user. `users` should be a concrete list/queryset
    (it's iterated twice: once for bulk_create, once to collect tokens).
    """
    users = list(users)

    notifications = create_bulk_notifications(
        users, title, body, notification_type=notification_type, payload=payload
    )

    if push:
        push_data = {
            "notification_type": notification_type,
            **(payload or {}),
        }
        send_push_to_users(users, title, body, data=push_data)

    return notifications


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
