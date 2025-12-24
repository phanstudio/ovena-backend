from paystackapi.paystack import Paystack
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

def initialize_paystack_transaction(amount, email):
    paystack = Paystack(secret_key=settings.PAYSTACK_SECRET_KEY)

    return paystack.transaction.initialize(
        amount=round(amount * 100),  # amount in kobo (5000 = ₦50.00)
        email=check_email_with_default(email),
    )

def check_email_with_default(email: str) -> str:
    try:
        validate_email(email)
        return email
    except ValidationError:
        return settings.DEFAULT_PAYMENT_EMAIL
