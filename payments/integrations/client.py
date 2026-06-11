from .paystack.client import PaystackClient
# from .base import BasePaymentClient

from django.conf import settings

def get_payment_client():
    provider = "paystack"#settings.PAYMENT_PROVIDER 

    if provider == "paystack":
        return PaystackClient()

    raise ValueError(f"Unknown provider: {provider}")


client = get_payment_client()
