"""
sale_service.py - initialize payment, complete service, process refund
"""
from payments.models import AbstractPayoutAccount
from payments.integrations.paystack.client import PaystackClient


paystack_client = PaystackClient()

def ensure_transfer_recipient(bank_account: AbstractPayoutAccount):
    payload = {
        "type": "nuban",
        "name": bank_account.bank_account_name,
        "account_number": bank_account.bank_account_number,
        "bank_code": bank_account.bank_code,
        "currency": "NGN",
    }
    recipient = paystack_client.create_transfer_recipient(payload).get("data", {})
    return recipient.get("recipient_code", "")

def _ensure_transfer_recipient(bank_account_name: str, bank_account_number: str, bank_code: str) -> str:
    payload = {
        "type": "nuban",
        "name": bank_account_name,
        "account_number": bank_account_number,
        "bank_code": bank_code,
        "currency": "NGN",
    }
    recipient = paystack_client.create_transfer_recipient(payload).get("data", {})
    return recipient.get("recipient_code")

def ensure_valid_cred(bank_account_number: str, bank_code: str) -> str:
    payload = {
        "account_number": bank_account_number,
        "bank_code": bank_code
    }
    recipient = paystack_client.verfy_account(payload).get("data", {})
    return recipient.get("account_name")
