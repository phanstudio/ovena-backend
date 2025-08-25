# from django.core.mail import send_mail
from django.conf import settings
import random, json, requests, time
from django.core.cache import cache

# def send_email_otp(email):
#     otp = generate_otp()
#     otp_store[email] = otp

#     send_mail(
#         subject="Your OTP Code",
#         message=f"Your OTP is {otp}. It expires in 5 minutes.",
#         from_email=settings.DEFAULT_FROM_EMAIL,
#         recipient_list=[email],
#         fail_silently=False,
#     )

#     return otp


def generate_otp(length=6):
    return "".join(str(random.randint(0, 9)) for _ in range(length))

def send_otp(phone_number):
    key = f"otp_data:{phone_number}"
    now = int(time.time())

    # Fetch existing record (OTP + attempts)
    data = cache.get(key)
    if data:
        data = json.loads(data)
        # Remove old attempts outside rate limit window
        data["attempts"] = [t for t in data.get("attempts", []) if now - t < settings.RATE_LIMIT_WINDOW]
        if len(data["attempts"]) >= settings.MAX_OTP_SENDS:
            return {"error": "Rate limit exceeded. Try again later."}
    else:
        data = {"otp": None, "attempts": []}

    # Generate new OTP and update attempts
    otp = generate_otp()
    data["otp"] = otp
    data["attempts"].append(now)

    # Store back with expiry = max of rate limit or OTP expiry
    cache.set(key, json.dumps(data), timeout=max(settings.RATE_LIMIT_WINDOW, settings.OTP_EXPIRY))

    # Send via Termii
    url = f"{settings.TERMII_BASE_URL}/api/sms/send"
    payload = {
        "to": phone_number,
        "from": settings.TERMII_SENDER_ID,
        "sms": f"Your pin is {otp}",
        "type": "plain",
        "channel": "generic",
        "api_key": settings.TERMII_API_KEY,
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, json=payload)
    print(response)
    return response.json()

def verify_otp(phone_number, otp_code):
    key = f"otp_data:{phone_number}"
    data = cache.get(key)
    if not data:
        return False

    data = json.loads(data)
    if data.get("otp") == otp_code:
        cache.delete(key)  # OTP is one-time use
        return True
    return False
