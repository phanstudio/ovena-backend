"""
Verification orchestration layer.

Strategy: Dojah is tried first for every check. Mono is used as a
fallback only where Mono exposes an equivalent single-call endpoint.
Three checks are Dojah-only by design - see the docstrings in
verification/integrations/mono/client.py for why:

    * BVN (personal + business) - Mono's BVN product needs an OTP
      round-trip with the BVN owner, not a silent server-side fallback.
    * Face match - Mono has no selfie/liveness/face-match product.
    * Plate number - Mono has no vehicle plate lookup product.

Every function here returns a plain dict and never raises:

    {
        "success": bool,
        "provider": "dojah" | "mono" | None,   # who actually answered
        "data": dict | None,
        "attempts": [ {"provider": "dojah", "error": "..."}, ... ],
    }

A failed result is a normal, expected outcome (bad NIN, provider
downtime, etc.) - callers should record it and route to manual review,
not treat it as a 500.
"""
import logging
import requests

from .integrations.dojah import client as dojah
from .integrations.mono import client as mono

logger = logging.getLogger(__name__)


def _dojah_error(exc: requests.RequestException) -> str:
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            return str(resp.json())
        except ValueError:
            return f"HTTP {resp.status_code}"
    return str(exc)


def _ok(provider, data, attempts):
    return {"success": True, "provider": provider, "data": data, "attempts": attempts}


def _fail(attempts):
    return {"success": False, "provider": None, "data": None, "attempts": attempts}


def _dojah_only(fn, *args, **kwargs) -> dict:
    attempts = []
    try:
        return _ok("dojah", fn(*args, **kwargs), attempts)
    except (requests.HTTPError, requests.RequestException) as exc:
        attempts.append({"provider": "dojah", "error": _dojah_error(exc)})
        return _fail(attempts)


def _dojah_then_mono(dojah_fn, dojah_args, mono_fn, mono_args) -> dict:
    attempts = []
    try:
        return _ok("dojah", dojah_fn(*dojah_args), attempts)
    except (requests.HTTPError, requests.RequestException) as exc:
        attempts.append({"provider": "dojah", "error": _dojah_error(exc)})

    result = mono_fn(*mono_args)
    if result["success"]:
        return _ok("mono", result["response_payload"], attempts)
    attempts.append({"provider": "mono", "error": result["error"]})
    return _fail(attempts)


# ── NIN ──────────────────────────────────────────────────────────────────

def verify_nin(nin: str) -> dict:
    return _dojah_then_mono(dojah.verify_nin, (nin,), mono.verify_nin, (nin,))


# ── BVN (Dojah only) ─────────────────────────────────────────────────────

def verify_bvn(bvn: str) -> dict:
    return _dojah_only(dojah.verify_bvn, bvn)


def validate_bvn(bvn: str, first_name: str = None, last_name: str = None, dob: str = None) -> dict:
    return _dojah_only(dojah.validate_bvn, bvn, first_name=first_name, last_name=last_name, dob=dob)


def verify_business_bvn(bvn: str) -> dict:
    return _dojah_only(dojah.verify_business_bvn, bvn)


# ── Face match (Dojah only) ──────────────────────────────────────────────

def match_face_to_name(image: str, first_name: str, last_name: str, bvn: str = None, nin: str = None) -> dict:
    return _dojah_only(dojah.match_face_to_name, image, first_name, last_name, bvn=bvn, nin=nin)


# ── Plate number (Dojah only) ────────────────────────────────────────────

def verify_plate_number(plate_number: str) -> dict:
    return _dojah_only(dojah.verify_plate_number, plate_number)


# ── Bank account / NUBAN ─────────────────────────────────────────────────

def verify_account_number(account_number: str, bank_code: str, nip_code: str = None) -> dict:
    """
    bank_code: Dojah/CBN bank code, used for the Dojah attempt.
    nip_code: Mono's own bank code, needed only for the Mono fallback
              (different scheme to bank_code - see mono/client.py).
              If omitted, the Mono fallback is skipped rather than
              guessed at.
    """
    attempts = []
    try:
        return _ok("dojah", dojah.verify_account_number(account_number, bank_code), attempts)
    except (requests.HTTPError, requests.RequestException) as exc:
        attempts.append({"provider": "dojah", "error": _dojah_error(exc)})

    if not nip_code:
        attempts.append({"provider": "mono", "error": "skipped: no nip_code supplied"})
        return _fail(attempts)

    result = mono.verify_account_number(account_number, nip_code)
    if result["success"]:
        return _ok("mono", result["response_payload"], attempts)
    attempts.append({"provider": "mono", "error": result["error"]})
    return _fail(attempts)


# ── TIN ──────────────────────────────────────────────────────────────────

def verify_tin(tin: str) -> dict:
    return _dojah_then_mono(dojah.verify_tin, (tin,), mono.verify_tin, (tin, "tin"))


# ── RC / CAC number ───────────────────────────────────────────────────────

def verify_rc_number(rc_number: str) -> dict:
    return _dojah_then_mono(dojah.verify_rc_number, (rc_number,), mono.verify_tin, (rc_number, "cac"))
