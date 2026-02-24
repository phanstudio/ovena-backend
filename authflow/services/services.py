import jwt
import datetime
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import User
import time
from django.utils import timezone
import secrets
import hashlib
import string
from django.core.mail import EmailMultiAlternatives
from datetime import timedelta
from .otp import OTPManager, OTPError, OTPRateLimitError, OTPDeliveryError, OTPInvalidError
from rest_framework.response import Response

OTP_TERM = "otp_lookup"

def create_token(user, role="main", scopes=None, expires_in=3600):
    """
    Create a JWT for a user with optional role + scopes.
    - user: Django User instance
    - role: "main" or "sub"
    - scopes: list of permissions (["read", "availability:update"])
    - expires_in: seconds (default: 1 hour)
    """
    if role == "main":
        if user is not User:
            return
        return issue_jwt_for_user(user)

    elif role == "sub":
        return make_sub_token(user['user_id'], user['device_id'], scopes, expires_in)

def make_sub_token(user_id, device_id="dyukljhgf4567890", scopes=None, expires_in=3600):
    now = datetime.datetime.now(datetime.timezone.utc)
    exp = now + datetime.timedelta(seconds=expires_in)
    payload = {
        "user_id": user_id,
        "device_id": device_id,
        "scopes": scopes or ["read"],
        "iat": now,
        "exp": exp,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

def issue_jwt_for_user(user: User):
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }

def start_time() -> float:
    start = time.perf_counter()
    return start

def calculate_time(start):
    duration = time.perf_counter() - start
    print(f"View took {duration:.4f} seconds")


def generate_passphrase(): # i can increase the size of this add rate limiting for this later
    words = ["mango", "horse", "bright", "storm", "leaf", "river", "cloud", "stone"]
    return "-".join(secrets.choice(words) for _ in range(2)) + "-" + str(secrets.randbelow(99))

def hash_phrase(phrase: str) -> str:
    return hashlib.sha256(phrase.encode()).hexdigest()

# When driver verifies:
def verify_delivery_phrase(order, entered_phrase):
    hashed = hash_phrase(entered_phrase)
    if hashed == order.delivery_secret_hash:
        order.status = "delivered"
        order.delivery_verified = True
        order.delivery_verified_at = timezone.now()
        order.save(update_fields=["status", "delivery_verified", "delivery_verified_at"])
        return True
    return False

def generate_referral_code(length=8):
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def send_otp_email(email: str, code: str, minutes_valid: int = 5) -> int:
    expires_at = timezone.now() + timedelta(minutes=minutes_valid)
    # Format like: Feb 12, 2026 18:14 (GMT+01:00)
    expires_str = expires_at.strftime("%b %d, %Y %H:%M")
    tz_str = expires_at.strftime("GMT%z")
    tz_str = tz_str[:-2] + ":" + tz_str[-2:]  # +0100 -> +01:00

    subject = "Your verification code"
    from_email = settings.DEFAULT_FROM_EMAIL
    to = [email]

    text_body = f"""Hi,

Use the following one-time password (OTP) to sign in.

This OTP will be valid for {minutes_valid} minutes till {expires_str} ({tz_str}).

{code}

If you didn't request this, you can ignore this email.
For help, contact {settings.SERVER_EMAIL}.

Regards,
{settings.PRODUCT_NAME if hasattr(settings, "PRODUCT_NAME") else "Support Team"}
{settings.WEBSITE_URL if hasattr(settings, "WEBSITE_URL") else ""}
"""

    # Host your logo somewhere stable (S3/Cloudinary/your CDN)
    logo_url = getattr(settings, "EMAIL_LOGO_URL", "")
    product_name = getattr(settings, "PRODUCT_NAME", "Newbutt")
    website_url = getattr(settings, "WEBSITE_URL", "https://newbutt.buzz/")
    support_email = settings.SERVER_EMAIL

    html_body = f"""
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f6f7fb;font-family:Arial,sans-serif;">
    <div style="max-width:560px;margin:0 auto;padding:24px;">
      <div style="background:#ffffff;border-radius:14px;padding:24px;border:1px solid #e8e9ee;">
        {"<div style='text-align:center;margin-bottom:16px;'><img src='"+logo_url+"' alt='"+product_name+"' style='height:36px;'/></div>" if logo_url else ""}
        <h2 style="margin:0 0 12px 0;color:#111827;font-size:20px;">Hi!</h2>
        <p style="margin:0 0 14px 0;color:#374151;font-size:14px;line-height:1.5;">
          Use the following one-time password (OTP) to sign in to your {product_name} account.
        </p>

        <div style="background:#f3f4f6;border:1px solid #e5e7eb;border-radius:12px;padding:18px;text-align:center;margin:18px 0;">
          <div style="font-size:28px;letter-spacing:6px;font-weight:700;color:#111827;">{code}</div>
        </div>

        <p style="margin:0 0 12px 0;color:#374151;font-size:13px;line-height:1.5;">
          This OTP will be valid for <b>{minutes_valid} minutes</b> till
          <b>{expires_str}</b> ({tz_str}).
        </p>

        <p style="margin:0 0 18px 0;color:#6b7280;font-size:12px;line-height:1.5;">
          If you didn't request this, you can safely ignore this email.
        </p>

        <hr style="border:none;border-top:1px solid #e5e7eb;margin:18px 0;" />

        <p style="margin:0;color:#6b7280;font-size:12px;line-height:1.5;">
          Need help? Contact <a href="mailto:{support_email}" style="color:#2563eb;text-decoration:none;">{support_email}</a><br/>
          <a href="{website_url}" style="color:#2563eb;text-decoration:none;">{website_url}</a>
        </p>
      </div>

      <p style="text-align:center;color:#9ca3af;font-size:11px;margin:14px 0 0 0;">
        © {product_name}. All rights reserved.
      </p>
    </div>
  </body>
</html>
"""

    msg = EmailMultiAlternatives(subject, text_body, from_email, to)
    msg.attach_alternative(html_body, "text/html")

    # returns number of accepted recipients (usually 1)
    return msg.send(fail_silently=False)


# ── Sending (views / tasks) ───────────────────────────────────────────────────
def request_otp(channel: str, identifier):
    try:
        OTPManager.send(channel=channel, identifier=identifier)
        sent_at = timezone.now()
        return Response({"detail": "OTP sent.", "sent_at": sent_at.strftime("%b %d, %Y %H:%M:%S %Z")})
    except OTPRateLimitError as e:
        return Response({"error": str(e)}, status=429)
    except OTPDeliveryError as e:
        return Response({"error": str(e)}, status=502)
    except OTPError as e: # catch-all for anything else
        return Response({"error": str(e)}, status=500)

def request_email_otp(email: str):
    return request_otp(channel="email", identifier=email)

def request_phone_otp(phone):
    return request_otp(channel="phone", identifier=phone)

# ── Verifying (works the same for email OR phone) ─────────────────────────────
def verify(otp_code, unverified_id):
    """
    Verifies Unverified ids with the otp code sent.
    """
    identifier = OTPManager.verify(otp_code=otp_code)
    if unverified_id != identifier:
        raise OTPInvalidError("Invalid OTP")
    return identifier