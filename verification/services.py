import requests
from django.conf import settings
from payments.integrations.paystack.client import PaystackClient

DOJAH_BASE_URL = "https://api.dojah.io"

paystack_client = PaystackClient()

def _headers():
    return {
        "AppId": settings.DOJAH_APP_ID,
        "Authorization": settings.DOJAH_SECRET_KEY,
        "Content-Type": "application/json",
    }


def _get(path, params=None):
    url = f"{DOJAH_BASE_URL}{path}"
    response = requests.get(url, headers=_headers(), params=params)
    response.raise_for_status()
    return response.json()


def _post(path, payload=None):
    url = f"{DOJAH_BASE_URL}{path}"
    response = requests.post(url, headers=_headers(), json=payload)
    response.raise_for_status()
    return response.json()


# ──────────────────────────────────────────────
# DRIVER VERIFICATIONS
# ──────────────────────────────────────────────

def verify_nin(nin: str) -> dict:
    """
    Look up a National Identification Number (NIN).
    Returns full identity data tied to the NIN.
    """
    return _get("/api/v1/kyc/nin", params={"nin": nin})


def verify_bvn(bvn: str) -> dict:
    """
    Look up a Bank Verification Number (BVN).
    Returns personal details tied to the BVN.
    """
    # return _get("/api/v1/kyc/bvn/full", params={"bvn": bvn})
    return paystack_client.verfy_bvn(bvn)


def validate_bvn(bvn: str, first_name: str = None, last_name: str = None, dob: str = None) -> dict:
    """
    Validate a BVN by matching it against supplied name/DOB.
    - dob format: YYYY-MM-DD
    Returns confidence scores and match status per field.
    """
    params = {"bvn": bvn}
    if first_name:
        params["first_name"] = first_name
    if last_name:
        params["last_name"] = last_name
    if dob:
        params["dob"] = dob
    return _get("/api/v1/kyc/bvn", params=params)


def verify_account_number(account_number: str, bank_code: str) -> dict:
    """
    Look up a NUBAN account number.
    - bank_code: CBN bank code e.g. "044" for Access Bank.
    Returns account name and bank details.
    """
    return _get("/api/v1/kyc/nuban", params={
        "account_number": account_number,
        "bank_code": bank_code,
    })


def match_face_to_name(
    image: str,
    first_name: str,
    last_name: str,
    bvn: str = None,
    nin: str = None,
) -> dict:
    """
    Match a selfie/face image against government ID data (BVN or NIN).
    - image: base64-encoded JPEG/PNG string.
    - Provide at least one of bvn or nin.
    Returns a match score and pass/fail status.
    """
    payload = {
        "image": image,
        "first_name": first_name,
        "last_name": last_name,
    }
    if bvn:
        payload["bvn"] = bvn
    if nin:
        payload["nin"] = nin
    return _post("/api/v1/kyc/photoid/verify", payload=payload)


def verify_plate_number(plate_number: str) -> dict:
    """
    Look up a Nigerian vehicle plate number.
    Returns vehicle registration data linked to the plate.
    """
    return _get("/api/v1/kyc/plate_number", params={"plate_number": plate_number})


# ──────────────────────────────────────────────
# BUSINESS VERIFICATIONS
# ──────────────────────────────────────────────

def verify_tin(tin: str) -> dict:
    """
    Verify a Tax Identification Number (TIN) via FIRS.
    Returns business name, tax office, and registration status.
    """
    return _get("/api/v1/kyc/tin", params={"tin": tin})


def verify_rc_number(rc_number: str) -> dict:
    """
    Look up a CAC RC (Registration) Number.
    Returns company name, directors, address, and status.
    """
    return _get("/api/v1/kyc/cac", params={"rc_number": rc_number})


def verify_business_bvn(bvn: str) -> dict:
    """
    Verify the BVN of a business owner/director.
    Same as individual BVN lookup but used in a business KYB context.
    """
    return _get("/api/v1/kyc/bvn/full", params={"bvn": bvn})
