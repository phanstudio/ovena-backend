# payments/exceptions.py

class PaymentError(Exception):
    """Base payment error."""


class TemporaryPaymentError(PaymentError):
    """Safe to retry automatically."""


class PermanentPaymentError(PaymentError):
    """Do not retry — bad input, auth, business-rule rejection."""