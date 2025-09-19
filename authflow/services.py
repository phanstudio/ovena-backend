import jwt
import datetime
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import User
import random, time
from django.core.cache import cache
from accounts.utils.otp import generate_otp

def create_token(user, role="main", scopes=[], expires_in=3600):
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
        return _issue_jwt_for_user(user)

    elif role == "sub":
        now = datetime.datetime.now(datetime.timezone.utc)
        exp = now + datetime.timedelta(seconds=expires_in)
        payload = {
            "user_id": user['user_id'],
            "device_id": user['device_id'],
            "scopes": scopes,
            "iat": now,
            "exp": exp,
        }

        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        return token

def _issue_jwt_for_user(user: User):
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }

def send_otp(user_id):
    now = int(time.time())

    # Rate limiting by user
    rate_key = f"otp_rate:{user_id}"
    attempts = cache.get(rate_key, [])
    attempts = [t for t in attempts if now - t < settings.RATE_LIMIT_WINDOW]

    if len(attempts) >= settings.MAX_OTP_SENDS:
        return {"error": "Rate limit exceeded. Try again later."}

    attempts.append(now)
    cache.set(rate_key, attempts, timeout=settings.RATE_LIMIT_WINDOW)

    # Generate OTP and ensure uniqueness
    for _ in range(5):  # try up to 5 times to avoid infinite loop
        otp = generate_otp()
        otp_key = f"otp_lookup:{otp}"
        if not cache.get(otp_key):
            cache.set(otp_key, user_id, timeout=settings.OTP_EXPIRY)
            break
    else:
        return {"error": "Could not generate unique OTP, try again."}

    # Normally you'd send SMS instead of returning
    return otp

def verify_otp(otp_code): # very non forgiving and an attempt limit later for wrong inputs
    otp_key = f"otp_lookup:{otp_code}"
    user_id = cache.get(otp_key)
    if not user_id:
        return None  # invalid or expired

    cache.delete(otp_key)  # one-time use
    return user_id

def start_time() -> float:
    start = time.perf_counter()
    return start

def calculate_time(start):
    duration = time.perf_counter() - start
    print(f"View took {duration:.4f} seconds")