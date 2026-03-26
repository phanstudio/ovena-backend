class PaystackClientError(Exception):
    """Base error for Paystack integration issues."""


class PaystackRequestError(PaystackClientError):
    """Network/HTTP/request-layer failure while calling Paystack."""


class PaystackAPIError(PaystackClientError):
    """Paystack responded but rejected/failed the request."""

    def __init__(self, message: str, status_code: int | None = None, payload: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}
