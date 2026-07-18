from payments.integrations.paystack.errors import PaystackAPIError, PaystackRequestError
from payments.integrations.errors import TemporaryPaymentError, PermanentPaymentError, PaymentError

# Known Paystack messages that indicate a transient, provider-side problem
# rather than a rejected/invalid request.
_TRANSIENT_MESSAGE_MARKERS = (
    "timeout",
    "timed out",
    "temporarily unavailable",
    "service unavailable",
    "try again",
    "internal server error",
    "gateway",
)


def classify_paystack_error(exc: Exception) -> PaymentError:
    """
    Map a Paystack client exception onto our internal
    Temporary/Permanent payment error hierarchy.
    """
    if isinstance(exc, PaystackRequestError):
        # Network/timeout/connection layer — always retryable
        return TemporaryPaymentError(str(exc))

    if isinstance(exc, PaystackAPIError):
        message = (exc.args[0] if exc.args else "").lower()
        if any(marker in message for marker in _TRANSIENT_MESSAGE_MARKERS):
            return TemporaryPaymentError(str(exc))
        return PermanentPaymentError(str(exc))

    # Unrecognized exception type — don't guess, surface it
    return PermanentPaymentError(str(exc))
