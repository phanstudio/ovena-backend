import time
import string
import secrets
import requests

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from datetime import timedelta


# ─── Exceptions ──────────────────────────────────────────────────────────────

class OTPError(Exception):
    """Base class for all OTP errors. Always safe to catch at the top level."""
    pass

class OTPRateLimitError(OTPError):
    """Raised when a channel's send rate limit is exceeded."""
    pass

class OTPGenerationError(OTPError):
    """Raised when a unique OTP cannot be generated (cache collision)."""
    pass

class OTPInvalidError(OTPError):
    """Raised when the supplied code is wrong or has already expired."""
    pass

class OTPDeliveryError(OTPError):
    """Raised when the underlying transport (email/SMS) fails to send."""
    pass


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _generate_code(length: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def _rate_limit_key(channel: str, identifier: str) -> str:
    # e.g. otp_rate:email:user@example.com  |  otp_rate:phone:+2348012345678
    return f"otp_rate:{channel}:{identifier}"


def _lookup_key(code: str) -> str:
    return f"otp_lookup:{code}"


# ─── Core OTP Manager ────────────────────────────────────────────────────────

class OTPManager:
    """
    Single, channel-aware OTP system.

    Storage strategy
    ----------------
    All channels use the reverse-lookup pattern:
        otp_lookup:<code>  →  identifier (email / phone / user_id / etc.)

    Rate limiting is per-channel so a phone flood never affects email quota:
        otp_rate:<channel>:<identifier>  →  [timestamp, ...]

    Usage
    -----
        # Send
        OTPManager.send(channel="email", identifier="user@example.com")
        OTPManager.send(channel="phone", identifier="+2348012345678")

        # Verify — returns the stored identifier on success
        verified = OTPManager.verify(otp_code="482910")

    Errors (all inherit OTPError)
    -----
        OTPRateLimitError   - too many sends on this channel
        OTPGenerationError  - couldn't mint a unique code (very rare)
        OTPInvalidError     - wrong / expired code
        OTPDeliveryError    - transport failure (email / SMS)
    """

    CHANNELS = ("email", "phone")

    # ── Public API ────────────────────────────────────────────────────────────

    @classmethod
    def send(cls, channel: str, identifier: str) -> None:
        """
        Rate-limit, generate, store, and deliver an OTP.
        Raises OTPRateLimitError, OTPGenerationError, or OTPDeliveryError.
        """
        if channel not in cls.CHANNELS:
            raise ValueError(f"Unknown OTP channel '{channel}'. Choose from {cls.CHANNELS}.")

        cls._enforce_rate_limit(channel, identifier)
        code = cls._mint_and_store(identifier)

        if channel == "email":
            cls._deliver_email(identifier, code)
        elif channel == "phone":
            cls._deliver_sms(identifier, code)

    @staticmethod  
    def verify(otp_code: str) -> str:
        """
        Verify a code regardless of channel.
        Only one caller can set the lock
        Returns the identifier (email / phone / etc.) on success.
        Raises OTPInvalidError if the code is wrong or expired.
        Deletes the key on success — one-time use.
        """
        key = _lookup_key(otp_code)
        lock_key = f"{key}:lock"

        # Only one caller can set the lock
        if not cache.add(lock_key, "1", timeout=10):
            raise OTPInvalidError("OTP is invalid or has expired.")

        identifier = cache.get(key)
        if not identifier:
            raise OTPInvalidError("OTP is invalid or has expired.")

        cache.delete(key)
        return identifier
    
    # ── Rate limiting ─────────────────────────────────────────────────────────

    @staticmethod
    def _enforce_rate_limit(channel: str, identifier: str) -> None:
        now = int(time.time())
        key = _rate_limit_key(channel, identifier)
        window = settings.RATE_LIMIT_WINDOW
        max_sends = settings.MAX_OTP_SENDS

        attempts: list[int] = cache.get(key, [])
        # Slide the window — drop timestamps older than the window
        attempts = [t for t in attempts if now - t < window]

        if len(attempts) >= max_sends:
            raise OTPRateLimitError(
                f"Too many OTP requests on channel '{channel}'. "
                f"Try again in {window // 60} minutes."
            )

        attempts.append(now)
        cache.set(key, attempts, timeout=window)

    # ── Code generation & storage ─────────────────────────────────────────────

    @staticmethod
    def _mint_and_store(identifier: str) -> str:
        """
        Generate a unique OTP and store it in the reverse-lookup cache.
        Retries up to 5 times on (astronomically unlikely) key collision.
        """
        for _ in range(5):
            code = _generate_code()
            key = _lookup_key(code)
            # cache.add is atomic: only sets if key does not exist
            if cache.add(key, identifier, timeout=settings.OTP_EXPIRY):
                return code
        raise OTPGenerationError(
            "Could not generate a unique OTP after 5 attempts. Please try again."
        )

    # ── Delivery ──────────────────────────────────────────────────────────────

    @staticmethod
    def _deliver_email(email: str, code: str, minutes_valid: int = 5) -> None:
        expires_at = timezone.now() + timedelta(minutes=minutes_valid)
        expires_str = expires_at.strftime("%b %d, %Y %H:%M")
        tz_str = expires_at.strftime("GMT%z")
        tz_str = tz_str[:-2] + ":" + tz_str[-2:]  # +0100 → +01:00

        product_name = getattr(settings, "PRODUCT_NAME", "Support Team")
        website_url  = getattr(settings, "WEBSITE_URL", "")
        logo_url     = getattr(settings, "EMAIL_LOGO_URL", "")
        support_email = settings.SERVER_EMAIL

        text_body = (
            f"Hi,\n\n"
            f"Your one-time password is: {code}\n\n"
            f"Valid for {minutes_valid} minutes (until {expires_str} {tz_str}).\n\n"
            f"If you didn't request this, ignore this email.\n"
            f"Help: {support_email}\n\n"
            f"{product_name}  {website_url}"
        )

        html_body = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px">
          {"<img src='" + logo_url + "' alt='" + product_name + "' height='40'><br><br>" if logo_url else ""}
          <p>Hi!</p>
          <p>Use the code below to verify your <strong>{product_name}</strong> account.</p>
          <div style="font-size:32px;font-weight:bold;letter-spacing:8px;margin:24px 0">{code}</div>
          <p>Valid for <strong>{minutes_valid} minutes</strong> — until {expires_str} ({tz_str}).</p>
          <p style="color:#888;font-size:13px">Didn't request this? You can safely ignore this email.</p>
          <hr>
          <p style="font-size:12px;color:#aaa">
            <a href="mailto:{support_email}">{support_email}</a> &nbsp;|&nbsp;
            <a href="{website_url}">{website_url}</a><br>
            &copy; {product_name}. All rights reserved.
          </p>
        </div>
        """

        msg = EmailMultiAlternatives(
            subject="Your verification code",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        )
        msg.attach_alternative(html_body, "text/html")

        try:
            msg.send(fail_silently=False)
        except Exception as exc:
            raise OTPDeliveryError(f"Failed to send OTP email to {email}: {exc}") from exc

    @staticmethod
    def _deliver_sms(phone_number: str, code: str) -> None:
        url = f"{settings.TERMII_BASE_URL}/api/sms/send"
        payload = {
            "to": phone_number,
            "from": settings.TERMII_SENDER_ID,
            "sms": f"Your verification code is {code}. Valid for {settings.OTP_EXPIRY // 60} minutes.",
            "type": "plain",
            "channel": "generic",
            "api_key": settings.TERMII_API_KEY,
        }
        try:
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OTPDeliveryError(f"Failed to send OTP SMS to {phone_number}: {exc}") from exc