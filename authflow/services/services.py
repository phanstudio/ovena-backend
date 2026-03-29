from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import User
from accounts.services.roles import get_user_roles
import time
from django.utils import timezone
import secrets
import hashlib
import string
from .otp import OTPManager, OTPError, OTPRateLimitError, OTPDeliveryError, OTPInvalidError
from rest_framework.response import Response

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

# passphrases:
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
