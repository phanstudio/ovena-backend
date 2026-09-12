import logging

from firebase_admin import messaging
from .models import DeviceToken

logger = logging.getLogger(__name__)


def _stringify_data(data):
    """FCM data payloads only accept string:string key/value pairs."""
    if not data:
        return {}
    return {str(k): str(v) for k, v in data.items()}


def send_push(token, title, body, data=None):
    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=_stringify_data(data),
        token=token,
    )
    return messaging.send(message)


def send_push_to_user(user, title, body, data=None):
    """
    Sends a push to every device registered for this user.
    Never raises — a Firebase/network failure here should not break
    the caller (e.g. the DB notification should still have been saved).
    Returns the BatchResponse, or None if the user has no tokens or
    the send failed outright.
    """
    tokens = list(user.device_tokens.values_list("token", flat=True))
    if not tokens:
        return None

    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data=_stringify_data(data),
        tokens=tokens,
    )

    try:
        response = messaging.send_each_for_multicast(message)
    except Exception:
        logger.exception("Firebase push failed for user_id=%s", user.pk)
        return None

    # clean up tokens that Firebase says are no longer valid
    invalid_tokens = []
    for idx, resp in enumerate(response.responses):
        if not resp.success and "Requested entity was not found" in str(resp.exception):
            invalid_tokens.append(tokens[idx])

    if invalid_tokens:
        DeviceToken.objects.filter(token__in=invalid_tokens).delete()

    return response


def send_push_to_users(users, title, body, data=None):
    """Bulk variant — sends to every device token across a list/queryset of users."""
    user_ids = [u.pk for u in users]
    if not user_ids:
        return None

    tokens = list(
        DeviceToken.objects.filter(user_id__in=user_ids).values_list("token", flat=True)
    )
    if not tokens:
        return None

    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data=_stringify_data(data),
        tokens=tokens,
    )

    try:
        response = messaging.send_each_for_multicast(message)
    except Exception:
        logger.exception("Firebase bulk push failed for %s users", len(user_ids))
        return None

    invalid_tokens = [
        tokens[idx]
        for idx, resp in enumerate(response.responses)
        if not resp.success and "Requested entity was not found" in str(resp.exception)
    ]
    if invalid_tokens:
        DeviceToken.objects.filter(token__in=invalid_tokens).delete()

    return response
