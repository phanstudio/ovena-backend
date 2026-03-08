from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from payments.integrations.paystack.client import PaystackClient


paystack_client = PaystackClient()


def initialize_paystack_transaction(amount, email):
    """
    Initialize a Paystack transaction using the unified PaystackClient.
    """
    payload = {
        "amount": round(amount * 100),  # amount in kobo (5000 = ₦50.00)
        "email": check_email_with_default(email),
    }
    return paystack_client.initialize_transaction(payload)


def check_email_with_default(email: str) -> str:
    try:
        validate_email(email)
        return email
    except ValidationError:
        return settings.DEFAULT_PAYMENT_EMAIL
