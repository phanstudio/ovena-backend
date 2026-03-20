from __future__ import annotations

from typing import Any, Callable

from django.conf import settings
from paystackapi.paystack import Paystack

from payments.integrations.paystack.errors import PaystackAPIError, PaystackRequestError


class PaystackClient:
    """
    Wrapper around the official/third-party `paystackapi` client.

    This keeps a single integration point (`PaystackClient`) while delegating
    request/response handling to the battle-tested SDK.
    """

    def __init__(self, secret_key: str | None = None, timeout: int = 20):
        # timeout kept for API compatibility, but handled by the SDK internally.
        self.secret_key = secret_key or getattr(settings, "PAYSTACK_SECRET_KEY", "")
        self.timeout = timeout
        self._client = Paystack(secret_key=self.secret_key)

    def _call(self, method: Callable[..., dict[str, Any]], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            result = method(**(payload or {}))
        except Exception as exc:  # pragma: no cover - defensive
            raise PaystackRequestError(str(exc)) from exc

        # `paystackapi` typically returns {"status": bool, "message": str, "data": {...}}
        if not isinstance(result, dict):
            raise PaystackRequestError("Unexpected response type from Paystack SDK")

        if not result.get("status"):
            message = result.get("message") or "Paystack request failed"
            raise PaystackAPIError(message=message, status_code=None, payload=result)

        return result

    def initialize_transaction(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call(self._client.transaction.initialize, payload)

    def refund(self, payload: dict[str, Any]) -> dict[str, Any]:
        # self._client.transaction.refund # fix refund
        return self._call(self._client.refund.create, payload)

    def create_transfer_recipient(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call(self._client.transferRecipient.create, payload)

    def initiate_transfer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call(self._client.transfer.initiate, payload)

    def bulk_transfer(self, payload: dict[str, Any]) -> dict[str, Any]:
        # self._client.transfer.bulk # was here before
        return self._call(self._client.transfer.initiate_bulk_transfer, payload)

    def fetch_transfer(self, transfer_code: str) -> dict[str, Any]:
        return self._call(self._client.transfer.verify, {"reference": transfer_code})

