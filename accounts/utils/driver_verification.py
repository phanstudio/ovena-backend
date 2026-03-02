"""
External verification service wrappers.

Mono  → NIN / BVN
Paystack → Bank account name resolution

Each function returns a dict:
    {
        "success": bool,
        "provider_ref": str,          # provider's transaction / reference id
        "response_payload": dict,     # full provider response
        "error": str | None,
    }
"""

import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


# ─── Mono ─────────────────────────────────────────────────────────────────────
# Docs: https://docs.mono.co/reference/identity-lookup

MONO_BASE_URL = "https://api.withmono.com/v2"
MONO_HEADERS = {
    "mono-sec-key": getattr(settings, "MONO_SECRET_KEY", ""),
    "Content-Type": "application/json",
}


def verify_nin_mono(nin: str) -> dict:
    """Verify a Nigerian NIN via Mono identity lookup."""
    url = f"{MONO_BASE_URL}/lookup/nin"
    payload = {"nin": nin}
    return _mono_request(url, payload, "nin")


def verify_bvn_mono(bvn: str) -> dict:
    """Verify a Nigerian BVN via Mono identity lookup."""
    url = f"{MONO_BASE_URL}/lookup/bvn"
    payload = {"bvn": bvn}
    return _mono_request(url, payload, "bvn")


def _mono_request(url: str, payload: dict, lookup_type: str) -> dict:
    try:
        resp = requests.post(url, json=payload, headers=MONO_HEADERS, timeout=15)
        data = resp.json()

        if resp.status_code == 200 and data.get("status") == "successful":
            return {
                "success": True,
                "provider_ref": data.get("id", ""),
                "response_payload": data,
                "error": None,
            }

        error_msg = data.get("message") or data.get("error") or f"HTTP {resp.status_code}"
        logger.warning("Mono %s verification failed: %s", lookup_type, error_msg)
        return {
            "success": False,
            "provider_ref": "",
            "response_payload": data,
            "error": error_msg,
        }

    except requests.RequestException as exc:
        logger.exception("Mono %s request error: %s", lookup_type, exc)
        return {
            "success": False,
            "provider_ref": "",
            "response_payload": {},
            "error": str(exc),
        }


# ─── Paystack ─────────────────────────────────────────────────────────────────
# Docs: https://paystack.com/docs/api/verification/#resolve-account

PAYSTACK_BASE_URL = "https://api.paystack.co"
PAYSTACK_HEADERS = {
    "Authorization": f"Bearer {getattr(settings, 'PAYSTACK_SECRET_KEY', '')}",
    "Content-Type": "application/json",
}


def verify_bank_account_paystack(account_number: str, bank_code: str) -> dict:
    """
    Resolve bank account name via Paystack.
    bank_code is the CBN bank code (e.g. '044' for Access Bank).
    The frontend should pass this alongside account_number.
    """
    url = f"{PAYSTACK_BASE_URL}/bank/resolve"
    params = {"account_number": account_number, "bank_code": bank_code}

    try:
        resp = requests.get(url, params=params, headers=PAYSTACK_HEADERS, timeout=15)
        data = resp.json()

        if resp.status_code == 200 and data.get("status") is True:
            resolved = data.get("data", {})
            return {
                "success": True,
                "provider_ref": resolved.get("account_number", ""),
                "account_name": resolved.get("account_name", ""),
                "response_payload": data,
                "error": None,
            }

        error_msg = data.get("message") or f"HTTP {resp.status_code}"
        logger.warning("Paystack bank verify failed: %s", error_msg)
        return {
            "success": False,
            "provider_ref": "",
            "account_name": "",
            "response_payload": data,
            "error": error_msg,
        }

    except requests.RequestException as exc:
        logger.exception("Paystack bank request error: %s", exc)
        return {
            "success": False,
            "provider_ref": "",
            "account_name": "",
            "response_payload": {},
            "error": str(exc),
        }