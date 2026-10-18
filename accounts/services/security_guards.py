from datetime import timedelta
from django.core.cache import cache
from django.utils import timezone
from rest_framework import serializers

SECURITY_COOLDOWN_SECONDS = 86400  # 24 hours
MAX_PIN_ATTEMPTS = 5
PIN_LOCKOUT_SECONDS = 1800  # 30 minutes

TRIVIAL_PINS = {
    "0000", "1111", "2222", "3333", "4444", "5555",
    "6666", "7777", "8888", "9999", "1234", "4321",
    "0123", "3210", "1122", "1212", "6969"
}


def validate_pin_format(pin: str):
    if not pin or not str(pin).isdigit() or len(str(pin)) != 4:
        raise serializers.ValidationError("Transaction PIN must be exactly 4 digits.")
    if str(pin) in TRIVIAL_PINS:
        raise serializers.ValidationError("This PIN is too common or easily guessed. Choose a more secure PIN.")


def is_pin_locked(user_id) -> tuple[bool, int]:
    """Returns (is_locked, remaining_seconds)."""
    key = f"pin_lock:{user_id}"
    ttl = cache.ttl(key) if hasattr(cache, "ttl") else None
    locked = cache.get(key)
    if locked:
        return True, ttl or PIN_LOCKOUT_SECONDS
    return False, 0


def record_failed_pin_attempt(user_id, ip_address: str | None = None) -> int:
    """Increments failed attempt counter; triggers 30-min lockout after MAX_PIN_ATTEMPTS and sends security alert email."""
    from django.contrib.auth import get_user_model
    from common.mail.services import send_security_alert_email

    attempts_key = f"pin_attempts:{user_id}"
    try:
        attempts = cache.incr(attempts_key)
    except Exception:
        cache.set(attempts_key, 1, timeout=PIN_LOCKOUT_SECONDS)
        attempts = 1

    if attempts >= MAX_PIN_ATTEMPTS:
        cache.set(f"pin_lock:{user_id}", True, timeout=PIN_LOCKOUT_SECONDS)
        cache.delete(attempts_key)

        # Notify user of security breach / lockout
        User = get_user_model()
        user = User.objects.filter(id=user_id).first()
        if user and getattr(user, "email", None):
            try:
                send_security_alert_email(
                    email=user.email,
                    alert_type="pin_lockout",
                    message="Your transaction PIN has been temporarily locked for 30 minutes due to 5 consecutive failed attempts.",
                    name=getattr(user, "first_name", None),
                    ip_address=ip_address,
                )
            except Exception:
                pass

    return attempts


def clear_pin_attempts(user_id):
    cache.delete(f"pin_attempts:{user_id}")
    cache.delete(f"pin_lock:{user_id}")


def set_security_cooldown(user, hours: int = 24, reason: str = "security credential update", ip_address: str | None = None):
    """Sets a withdrawal cooldown on the user following a sensitive credential change and alerts the user."""
    from common.mail.services import send_security_alert_email

    key = f"security_cooldown:{user.id}"
    cache.set(key, timezone.now().isoformat(), timeout=hours * 3600)

    if getattr(user, "email", None):
        try:
            send_security_alert_email(
                email=user.email,
                alert_type="credential_change",
                message=f"A sensitive change ({reason}) was performed on your account. A {hours}-hour security cooldown has been applied to all withdrawals to protect your funds.",
                name=getattr(user, "first_name", None),
                ip_address=ip_address,
            )
        except Exception:
            pass


def is_security_cooldown_active(user) -> tuple[bool, int]:
    """Returns (is_active, remaining_seconds)."""
    key = f"security_cooldown:{user.id}"
    val = cache.get(key)
    if not val:
        # Also check UserAccount last_bank_change_at if present
        payment_account = getattr(user, "payment_account", None)
        if payment_account and payment_account.last_bank_change_at:
            elapsed = (timezone.now() - payment_account.last_bank_change_at).total_seconds()
            if elapsed < SECURITY_COOLDOWN_SECONDS:
                return True, int(SECURITY_COOLDOWN_SECONDS - elapsed)
        return False, 0

    return True, SECURITY_COOLDOWN_SECONDS
