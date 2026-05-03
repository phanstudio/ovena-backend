import requests
from django.conf import settings

TERMII_BASE_URL = settings.TERMII_BASE_URL
OTP_EXPIRY = settings.OTP_EXPIRY
TERMII_API_KEY = settings.TERMII_API_KEY
TERMII_SENDER_ID = settings.TERMII_SENDER_ID

PIN_LENGTH = 5
OTP_EXPIRY_MINUTES = OTP_EXPIRY // settings.MINUTE


def send_regular_sms(phone_number, sms):
    url = f"{TERMII_BASE_URL}/api/sms/send"
    payload = {
        "to": phone_number,
        "from": TERMII_SENDER_ID,
        "sms": sms,
        "type": "plain",
        "channel": "generic",
        "api_key": TERMII_API_KEY,
    }

    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    response.raise_for_status()


def send_otp_sms(phone_number) -> str:
    url = f"{TERMII_BASE_URL}/api/sms/otp/send"
    payload = {
        "api_key" : TERMII_API_KEY,
        "message_type" : "NUMERIC",
        "to" : phone_number,
        "from" : TERMII_SENDER_ID,
        "channel" : "generic",
        "pin_attempts" : 10,
        "pin_time_to_live" :  OTP_EXPIRY_MINUTES,
        "pin_length" : PIN_LENGTH,
        "pin_placeholder" : "< 12345678 >",
        "message_text" : "Your pin is to authenticate your transaction is < 12345678 >",
        "pin_type" : "NUMERIC"
    }

    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    pin_id = response.json().get("pin_id")
    return pin_id


def verify_otp(otp_id, code):
    url = f"{TERMII_BASE_URL}/api/sms/otp/verify"
    payload = {
        "api_key": TERMII_API_KEY,
        "pin_id": otp_id,
        "pin": code
    }

    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    return data['verified'], data['msisdn']
