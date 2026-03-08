from __future__ import annotations

from typing import Any

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from payments.integrations.paystack.errors import PaystackAPIError, PaystackRequestError


class PaystackClient:
    """Thin Paystack client with default timeout and retry behavior."""

    def __init__(self, secret_key: str | None = None, timeout: int = 20):
        self.base_url = "https://api.paystack.co"
        self.secret_key = secret_key or getattr(settings, "PAYSTACK_SECRET_KEY", "")
        self.timeout = timeout
        self.session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, json_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = self.session.request(
                method=method,
                url=url,
                json=json_payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise PaystackRequestError(str(exc)) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise PaystackRequestError(f"Non-JSON response from Paystack ({response.status_code})") from exc

        if response.status_code not in (200, 201) or not payload.get("status"):
            message = payload.get("message") or f"Paystack request failed ({response.status_code})"
            raise PaystackAPIError(message=message, status_code=response.status_code, payload=payload)

        return payload

    def initialize_transaction(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/transaction/initialize", payload)

    def refund(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/refund", payload)

    def create_transfer_recipient(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/transferrecipient", payload)

    def initiate_transfer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/transfer", payload)

    def bulk_transfer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/transfer/bulk", payload)

    def fetch_transfer(self, transfer_code: str) -> dict[str, Any]:
        return self._request("GET", f"/transfer/{transfer_code}")

