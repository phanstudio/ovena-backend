from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import User
from accounts.services.roles import get_user_roles
import time
from django.utils import timezone
import secrets
import string
from .otp import OTPManager, OTPError, OTPRateLimitError, OTPDeliveryError, OTPInvalidError
from rest_framework.response import Response
from django.db import IntegrityError
from .delivery import hash_phrase

def issue_jwt_for_user(user: User, *, active_profile: str | None = None):
    refresh = RefreshToken.for_user(user)
    refresh.access_token["roles"] = sorted(get_user_roles(user))
    if active_profile:
        refresh.access_token["active_profile"] = active_profile
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }

# time:
def start_time() -> float:
    start = time.perf_counter()
    return start

def calculate_time(start):
    duration = time.perf_counter() - start
    print(f"View took {duration:.4f} seconds")

def mint_driver_pin(order):
    digits = string.digits

    for _ in range(5):  # small retry cap
        code = ''.join(secrets.choice(digits) for _ in range(6))

        try:
            order.driver_number = code
            order.save(update_fields=["driver_number"])
            return code

        except IntegrityError:
            continue

    raise Exception("Failed to generate unique PIN")

# When driver verifies:
#:old broken
def verify_resturant_otp(order, otp):
    hashed = hash_phrase(str(otp))
    driver_hash = hash_phrase(str(order.driver_number))
    if hashed == driver_hash:
        return True
    return False

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

def request_phone_otp(phone, external=True):
    if not external:
        return request_otp(channel="phone", identifier=phone)
    else:
        try:
            pin_id = OTPManager.deliver_sms_externally(phone)
            sent_at = timezone.now()
            return Response({"detail": "OTP sent.", "sent_at": sent_at.strftime("%b %d, %Y %H:%M:%S %Z"), 'pin_id': pin_id})
        except OTPDeliveryError as e:
            return Response({"error": str(e)}, status=502)
        except OTPError as e: # catch-all for anything else
            return Response({"error": str(e)}, status=500)

# ── Verifying (works the same for email OR phone) ─────────────────────────────
def verify(otp_code, unverified_id):
    """
    Verifies Unverified ids with the otp code sent.
    """
    identifier = OTPManager.verify(otp_code=otp_code)
    if unverified_id != identifier:
        raise OTPInvalidError("Invalid OTP")
    return identifier

def verify_phonenumber(otp_code, unverified_id, pin_id):
    """
    Verifies Unverified ids with the otp code sent.
    """
    identifier = OTPManager.verify_externally(pin_id, code=otp_code)
    if unverified_id != identifier:
        raise OTPInvalidError("Invalid OTP")
    return identifier
