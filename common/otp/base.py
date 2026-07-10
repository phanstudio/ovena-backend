import time
import string
import secrets
import requests

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from datetime import timedelta
from common.mail.services import send_email
from common.mail.template import maling_temp
from common.phone.services import send_regular_sms, OTP_EXPIRY_MINUTES, send_otp_sms, verify_otp
from .exceptions import *

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
    
    @classmethod
    def send_code(cls, channel: str, identifier: str, code:str) -> None:
        """
        Rate-limit, generate, store, and deliver an OTP.
        Raises OTPRateLimitError, OTPGenerationError, or OTPDeliveryError.
        """
        if channel not in cls.CHANNELS:
            raise ValueError(f"Unknown OTP channel '{channel}'. Choose from {cls.CHANNELS}.")

        cls._enforce_rate_limit(channel, identifier)

        if channel == "email":
            cls._deliver_email(identifier, code)
        elif channel == "phone":
            cls._deliver_sms(identifier, code)
    
    @staticmethod
    def send_blank(identifier: str) -> str:
        """
        Rate-limit, generate, store, and deliver an OTP.
        Raises OTPRateLimitError, OTPGenerationError, or OTPDeliveryError.
        """
        OTPManager._enforce_rate_limit("none", identifier)
        code = OTPManager._mint_and_store(identifier)
        return code

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
    
    @staticmethod
    def _store(key:str, identifier: str) -> str:
        """
        Generate a unique OTP and store it in the reverse-lookup cache.
        Retries up to 5 times on (astronomically unlikely) key collision.
        """
        new_key = _lookup_key(key)
        # cache.add is atomic: only sets if key does not exist
        if cache.add(new_key, identifier, timeout=settings.OTP_EXPIRY):
            return new_key
        raise OTPGenerationError(
            "Could not generate a unique OTP after 5 attempts. Please try again."
        )

    # ── Delivery ──────────────────────────────────────────────────────────────

    @staticmethod
    # def _deliver_email(email: str, code: str, minutes_valid: int = 5) -> None:
    #     expires_at = timezone.now() + timedelta(minutes=minutes_valid)
    #     expires_str = expires_at.strftime("%b %d, %Y %H:%M")
    #     tz_str = expires_at.strftime("GMT%z")
    #     tz_str = tz_str[:-2] + ":" + tz_str[-2:]  # +0100 → +01:00

    #     product_name = getattr(settings, "PRODUCT_NAME", "Support Team")
    #     website_url  = getattr(settings, "WEBSITE_URL", "")
    #     logo_url     = getattr(settings, "EMAIL_LOGO_URL", "")
    #     support_email = settings.SERVER_EMAIL

    #     text_body = (
    #         f"Hi,\n\n"
    #         f"Your one-time password is: {code}\n\n"
    #         f"Valid for {minutes_valid} minutes (until {expires_str} {tz_str}).\n\n"
    #         f"If you didn't request this, ignore this email.\n"
    #         f"Help: {support_email}\n\n"
    #         f"{product_name}  {website_url}"
    #     )

    #     html_body = f"""
    #     <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px">
    #       {"<img src='" + logo_url + "' alt='" + product_name + "' height='40'><br><br>" if logo_url else ""}
    #       <p>Hi!</p>
    #       <p>Use the code below to verify your <strong>{product_name}</strong> account.</p>
    #       <div style="font-size:32px;font-weight:bold;letter-spacing:8px;margin:24px 0">{code}</div>
    #       <p>Valid for <strong>{minutes_valid} minutes</strong> — until {expires_str} ({tz_str}).</p>
    #       <p style="color:#888;font-size:13px">Didn't request this? You can safely ignore this email.</p>
    #       <hr>
    #       <p style="font-size:12px;color:#aaa">
    #         <a href="mailto:{support_email}">{support_email}</a> &nbsp;|&nbsp;
    #         <a href="{website_url}">{website_url}</a><br>
    #         &copy; {product_name}. All rights reserved.
    #       </p>
    #     </div>
    #     """

    #     msg = EmailMultiAlternatives(
    #         subject="Your verification code",
    #         body=text_body,
    #         from_email=settings.DEFAULT_FROM_EMAIL,
    #         to=[email],
    #     )
    #     msg.attach_alternative(html_body, "text/html")

    #     try:
    #         send_email(msg)
    #         # msg.send(fail_silently=False)
    #     except Exception as exc:
    #         raise OTPDeliveryError(f"Failed to send OTP email to {email}: {exc}") from exc

    @staticmethod
    def _deliver_email(email: str, code: str, minutes_valid: int = 60) -> None:
        expires_at = timezone.now() + timedelta(minutes=minutes_valid)
        expires_str = expires_at.strftime("%b %d, %Y %H:%M")
        tz_str = expires_at.strftime("GMT%z")
        tz_str = tz_str[:-2] + ":" + tz_str[-2:]  # +0100 → +01:00

        product_name = getattr(settings, "PRODUCT_NAME", "Support Team")
        website_url = getattr(settings, "WEBSITE_URL", "")
        logo_url = getattr(settings, "EMAIL_LOGO_URL", "")
        support_email = settings.SERVER_EMAIL

        # Plain‑text version (keep consistent)
        text_body = (
            f"Help us protect your account\n\n"
            f"Before you sign in, we need to verify your identity. "
            f"Enter the following code on the sign‑in page.\n\n"
            f"{code}\n\n"
            f"If you have not recently tried to sign into {product_name}, "
            f"we recommend changing your password and setting up Two‑Factor Authentication "
            f"to keep your account safe. Your verification code expires after "
            f"{minutes_valid} minutes (until {expires_str} {tz_str}).\n\n"
            f"---\n"
            f"You're receiving this email because of your account on {website_url}.\n"
            f"Manage all notifications: {website_url}/-/profile/notifications\n"
            f"Help: {website_url}/help"
        )
        html_body = maling_temp(
            product_name, website_url, logo_url, support_email, minutes_valid, code
        )
        # HTML version – GitLab style
        # html_body = f"""
        # <div style="text-align:center;min-width:640px;width:100%;height:100%;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;margin:0;padding:0" bgcolor="#fafafa">
        # <table border="0" cellpadding="0" cellspacing="0" id="body" style="text-align:center;min-width:640px;width:100%;margin:0;padding:0" bgcolor="#fafafa">
        # <tbody>
        #     <!-- Top purple bar -->
        #     <tr>
        #         <td style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;height:4px;font-size:4px;line-height:4px" bgcolor="#6b4fbb"></td>
        #     </tr>
        #     <!-- Logo (top) -->
        #     <tr>
        #         <td style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:13px;line-height:1.6;color:#5c5c5c;padding:25px 0">
        #             {"<img alt='" + product_name + "' src='" + logo_url + "' width='55' height='55'>" if logo_url else "<span style='font-size:24px;font-weight:bold;color:#303030'>" + product_name + "</span>"}
        #         </td>
        #     </tr>
        #     <!-- Main card -->
        #     <tr>
        #         <td style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif">
        #             <table border="0" cellpadding="0" cellspacing="0" class="wrapper" style="width:640px;border-collapse:separate;border-spacing:0;margin:0 auto">
        #                 <tbody>
        #                     <tr>
        #                         <td class="wrapper-cell" style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;border-radius:3px;overflow:hidden;padding:18px 25px;border:1px solid #ededed" align="left" bgcolor="#ffffff">
        #                             <table border="0" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:separate;border-spacing:0">
        #                                 <tbody>
        #                                     <tr>
        #                                         <td>
        #                                             <div style="color:#1f1f1f;line-height:1.25em;max-width:400px;margin:0 auto" align="center">
        #                                                 <h3 style="font-size:1.3em;font-weight:500;margin:0 0 0.5em">Help us protect your account</h3>
        #                                                 <p style="font-size:0.9em;margin:0 0 1.5em">
        #                                                     Before you sign in, we need to verify your identity.
        #                                                     Enter the following code on the sign‑in page.
        #                                                 </p>
        #                                                 <div style="width:207px;height:53px;background-color:#f0f0f0;line-height:53px;font-weight:700;font-size:1.5em;color:#303030;margin:26px auto;border-radius:3px;letter-spacing:2px">
        #                                                     {code}
        #                                                 </div>
        #                                                 <p style="font-size:0.75em;color:#5c5c5c;margin:1.5em 0 0">
        #                                                     If you have not recently tried to sign into {product_name},
        #                                                     we recommend changing your password and setting up
        #                                                     Two‑Factor Authentication to keep your account safe.
        #                                                     Your verification code expires after {minutes_valid} minutes.
        #                                                 </p>
        #                                             </div>
        #                                         </td>
        #                                     </tr>
        #                                 </tbody>
        #                             </table>
        #                         </td>
        #                     </tr>
        #                 </tbody>
        #             </table>
        #         </td>
        #     </tr>
        #     <!-- Footer -->
        #     <tr>
        #         <td style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:13px;line-height:1.6;color:#5c5c5c;padding:25px 0">
        #             {"<img alt='" + product_name + "' src='" + logo_url + "' style='display:block;width:90px;margin:0 auto 1em'>" if logo_url else ""}
        #             <div>
        #                 You're receiving this email because of your account on
        #                 <a href="{website_url}" style="color:#3777b0;text-decoration:none">{website_url}</a>.
        #                 <a href="{website_url}/-/profile/notifications" style="color:#3777b0;text-decoration:none">Manage all notifications</a> ·
        #                 <a href="{website_url}/help" style="color:#3777b0;text-decoration:none">Help</a>
        #             </div>
        #             <div style="margin-top:1em;font-size:12px;color:#aaa">
        #                 <a href="mailto:{support_email}" style="color:#3777b0;text-decoration:none">{support_email}</a>
        #             </div>
        #         </td>
        #     </tr>
        # </tbody>
        # </table>
        # </div>
        # """

        msg = EmailMultiAlternatives(
            subject="Your verification code",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        )
        msg.attach_alternative(html_body, "text/html")

        try:
            send_email(msg)
        except Exception as exc:
            raise OTPDeliveryError(f"Failed to send OTP email to {email}: {exc}") from exc

    @staticmethod
    def _deliver_sms(phone_number: str, code: str) -> None:
        sms = f"Your verification code is {code}. Valid for {OTP_EXPIRY_MINUTES} minutes."
        try:
            send_regular_sms(phone_number, sms)
        except requests.RequestException as exc:
            raise OTPDeliveryError(f"Failed to send OTP SMS to {phone_number}: {exc}") from exc
    
    # ── External Delivery ──────────────────────────────────────────────────────────────
    @staticmethod
    def deliver_sms_externally(phone_number) -> str:
        try:
            pin_id = send_otp_sms(phone_number)
            return pin_id
        except requests.RequestException as exc:
            raise OTPDeliveryError(f"Failed to send OTP SMS to {phone_number}: {exc}") from exc
    
    @staticmethod
    def verify_externally(otp_id:str, code: str):
        try:
            verified, identifier = verify_otp(otp_id, code)
            if verified:
                return identifier
            else:
                raise requests.RequestException
        except requests.RequestException as exc:
            raise OTPInvalidError("OTP is invalid or has expired.")

# we need a fall back for the phonenumber like whatsapp or email after a certain time.
