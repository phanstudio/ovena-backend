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
    
    def verfy_bvn_match(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call(self._client.verification.verify_bvn_match, payload)
    
    def verfy_bvn(self, bvn: str) -> dict[str, Any]:
        return self._call(self._client.verification.verify_bvn, {"bvn": bvn})
    
    def verfy_account(self, payload: dict[str, Any]) ->  dict[str, Any]:
        return self._call(self._client.verification.verify_account, payload) 
    
    def create_customer(self, payload: dict[str, Any]) ->  dict[str, Any]:
        """
        Create a customer in Paystack.

        payload = {
            "email": email,
            "first_name": first_name, <opt>
            "last_name": last_name, <opt>
        }
        """
        return self._call(self._client.customer.create, payload)
    
    def create_subscription(self, payload: dict[str, Any]) ->  dict[str, Any]:
        """
        Create a subscription in Paystack.
            
        payload = {
            "customer": customer_code,
            "plan": plan_code,
            "metadata": metadata or {},
        }
        """
        return self._call(self._client.subscription.create, payload)

    def disable_subscription(self, payload: dict[str, Any]) ->  dict[str, Any]:
        """
        Disable a subscription (cancel at Paystack).

        payload = {
            "code": subscription_code,
            "token": email_token, <opt>
        }
        """
        return self._call(self._client.subscription.disable, payload)

    def fetch_subscription(self, subscription_code: str) -> dict[str, Any]:
        """Fetch subscription details from Paystack."""
        return self._call(self._client.subscription.fetch, {"subscription_code": subscription_code})

    def create_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Create a recurring plan on Paystack.

        payload = {
            "name": str,
            "interval": "daily" | "weekly" | "monthly" | "yearly",
            "amount": int,          # in kobo (lowest denomination)
            "description": str,     # optional
            "send_invoices": bool,  # optional
            "send_sms": bool,       # optional
            "currency": str,        # default "NGN"
        }
        """
        return self._call(self._client.plan.create, payload)

    def update_plan(self, plan_code: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Update an existing plan (only name, description, amount? Paystack allows limited fields).
        Note you can't change interval after subscription.

        payload = {
            "name": str,
            "description": str,
            "amount": int,   # optional, but cannot be increased after subscriptions exist
        }
        """
        # Note: Paystack endpoint is PUT /plan/:code
        # The SDK might have plan.update(plan_code, **payload)
        # If not, you may need a raw request. Assuming the SDK has:
        return self._call(lambda: self._client.plan.update(plan_code, **payload))

    def get_subscription_update_link(self, subscription_code: str) -> dict[str, Any]: #:bad #:depeciated
        """Generate a hosted link for the customer to update their card."""
        return self._call(
            self._client.subscription.generate_update_subscription_link,
            {"subscription_code": subscription_code}
        )

    def send_subscription_update_email(self, subscription_code: str) -> dict[str, Any]: #:bad #:depeciated
        """Trigger Paystack to email the customer a card-update link."""
        return self._call(
            self._client.subscription.send_update_subscription_link,
            # self._client.subscription.manage_email,
            {"subscription_code": subscription_code}
        )

    def verify_transaction(self, reference:str):
        return self._call(
            self._client.transaction.verify,
            {"reference": reference}
        )
        

    # def newone(self):
    #     # self._call
    #     self._client.transaction.verify()
