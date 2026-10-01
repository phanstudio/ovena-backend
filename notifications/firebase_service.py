import json
import logging
from firebase_admin import messaging, exceptions as fb_exceptions
from .models import DeviceToken

logger = logging.getLogger(__name__)

FCM_MULTICAST_BATCH_SIZE = 500


def _stringify_data(data):
    """FCM data payloads only accept string:string key/value pairs with valid JSON."""
    if not data:
        return {}
    result = {}
    for k, v in data.items():
        if isinstance(v, (dict, list, bool)):
            result[str(k)] = json.dumps(v)
        elif v is None:
            result[str(k)] = ""
        else:
            result[str(k)] = str(v)
    return result


def _is_invalid_token_error(exc):
    """Check if the FCM exception indicates the token is dead or invalid."""
    if exc is None:
        return False
    if isinstance(exc, (messaging.UnregisteredError, messaging.SenderIdMismatchError)):
        return True
    exc_str = str(exc).lower()
    return any(
        phrase in exc_str
        for phrase in (
            "not a valid fcm registration token",
            "requested entity was not found",
            "unregistered",
            "invalid registration",
        )
    )


def _build_android_config():
    return messaging.AndroidConfig(
        priority="high",
        notification=messaging.AndroidNotification(
            sound="default",
            default_sound=True,
            channel_id="default_channel",
        ),
    )


def _build_apns_config():
    return messaging.APNSConfig(
        payload=messaging.APNSPayload(
            aps=messaging.Aps(
                sound="default",
                content_available=True,
            )
        )
    )


def send_dummy_message():
    key = "Y"
    send_push(key, "love", "love")


def send_push(token, title, body, data=None):
    """Single device push with error handling."""
    if not token:
        return None

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=_stringify_data(data),
        token=token,
        android=_build_android_config(),
        apns=_build_apns_config(),
    )
    try:
        return messaging.send(message)
    except Exception as e:
        logger.warning("FCM single push failed for token %s: %s", token[:10], e)
        if _is_invalid_token_error(e):
            DeviceToken.objects.filter(token=token).delete()
        return None


def send_push_to_user(user, title, body, data=None):
    """Sends a push to every device registered for this user."""
    tokens = list(user.device_tokens.values_list("token", flat=True))
    if not tokens:
        return None

    invalid_tokens = []
    responses = []

    for i in range(0, len(tokens), FCM_MULTICAST_BATCH_SIZE):
        batch_tokens = tokens[i : i + FCM_MULTICAST_BATCH_SIZE]
        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data=_stringify_data(data),
            tokens=batch_tokens,
            android=_build_android_config(),
            apns=_build_apns_config(),
        )

        try:
            batch_resp = messaging.send_each_for_multicast(message)
            responses.append(batch_resp)
            for idx, resp in enumerate(batch_resp.responses):
                if not resp.success and _is_invalid_token_error(resp.exception):
                    invalid_tokens.append(batch_tokens[idx])
        except Exception:
            logger.exception("Firebase push failed for user_id=%s", user.pk)

    if invalid_tokens:
        DeviceToken.objects.filter(token__in=invalid_tokens).delete()

    return responses


def send_push_to_users(users, title, body, data=None):
    """Bulk variant across multiple users, safely chunked in batches of 500."""
    user_ids = [u.pk for u in users]
    if not user_ids:
        return None

    tokens = list(
        DeviceToken.objects.filter(user_id__in=user_ids).values_list("token", flat=True)
    )
    if not tokens:
        return None

    invalid_tokens = []
    responses = []

    for i in range(0, len(tokens), FCM_MULTICAST_BATCH_SIZE):
        batch_tokens = tokens[i : i + FCM_MULTICAST_BATCH_SIZE]
        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data=_stringify_data(data),
            tokens=batch_tokens,
            android=_build_android_config(),
            apns=_build_apns_config(),
        )

        try:
            batch_resp = messaging.send_each_for_multicast(message)
            responses.append(batch_resp)
            for idx, resp in enumerate(batch_resp.responses):
                if not resp.success and _is_invalid_token_error(resp.exception):
                    invalid_tokens.append(batch_tokens[idx])
        except Exception:
            logger.exception("Firebase bulk push failed for %s users", len(user_ids))

    if invalid_tokens:
        DeviceToken.objects.filter(token__in=invalid_tokens).delete()

    return responses
