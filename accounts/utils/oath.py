# from django.conf import settings
# import jwt
# import requests
# from jwt.algorithms import RSAAlgorithm

# APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"

# def verify_apple_token(token):
#     keys = requests.get(APPLE_KEYS_URL, timeout=120).json()['keys']
#     header = jwt.get_unverified_header(token)

#     key = next(k for k in keys if k['kid'] == header['kid'])
#     public_key = RSAAlgorithm.from_jwk(key)

#     payload = jwt.decode(
#         token,
#         public_key,
#         audience=settings.APPLE_SERVICE_ID,
#         issuer="https://appleid.apple.com",
#         algorithms=["RS256"]
#     )
#     return payload


"""
Apple token verification, kept separate from business logic (accounts/utils/oath.py
or wherever verify_apple_token currently lives). Google verification isn't shown here
since GoogleAuthSerializer already handles it via whatever library you're using
(google-auth / social libs) and wasn't part of what broke.

Add to settings.py:

    APPLE_ISSUER = "https://appleid.apple.com"
    APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
    APPLE_AUDIENCE = "com.yourcompany.yourapp"   # your bundle ID or Services ID
    APPLE_JWKS_CACHE_TTL = 60 * 60               # 1 hour

Requires: pip install pyjwt httpx
"""

import json
import time

import httpx
import jwt
from django.conf import settings
from rest_framework.exceptions import ValidationError
from rest_framework import serializers
from google.oauth2 import id_token  # type: ignore
from google.auth.transport import requests  # type: ignore

_jwks_cache = {"keys": None, "fetched_at": 0}


def _get_apple_jwks(force_refresh: bool = False):
    now = time.time()
    ttl = getattr(settings, "APPLE_JWKS_CACHE_TTL", 3600)

    if force_refresh or _jwks_cache["keys"] is None or now - _jwks_cache["fetched_at"] > ttl:
        resp = httpx.get(settings.APPLE_JWKS_URL, timeout=5)
        resp.raise_for_status()
        _jwks_cache["keys"] = resp.json()["keys"]
        _jwks_cache["fetched_at"] = now

    return _jwks_cache["keys"]


def verify_apple_token(id_token: str) -> dict:
    """
    Verifies signature, issuer, audience, and expiration.
    Returns the decoded payload (includes `sub`, and `email` only on
    the user's first-ever authorization — do not assume it's present).
    """
    if not id_token:
        raise ValidationError({"id_token": "This field is required."})

    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError:
        raise ValidationError({"id_token": "Malformed token."})

    kid = header.get("kid")
    keys = _get_apple_jwks()
    key_data = next((k for k in keys if k["kid"] == kid), None)

    if key_data is None:
        # Apple rotated keys since our cache — refresh once and retry
        keys = _get_apple_jwks(force_refresh=True)
        key_data = next((k for k in keys if k["kid"] == kid), None)
        if key_data is None:
            raise ValidationError({"id_token": "Apple signing key not found."})

    public_key = jwt.PyJWK.from_json(json.dumps(key_data)).key

    try:
        payload = jwt.decode(
            id_token,
            key=public_key,
            algorithms=["RS256"],
            audience=settings.APPLE_AUDIENCE,
            issuer=settings.APPLE_ISSUER,
        )
    except jwt.PyJWTError as e:
        raise ValidationError({"id_token": f"Invalid Apple token: {e}"})

    return payload


def verify_google_token(google_id_token: str):
    try:
        client_id = settings.OAUTH_PROVIDERS.get("google").get("CLIENT_ID")
        info = id_token.verify_oauth2_token(
            google_id_token, requests.Request(), client_id
        )
    except Exception as e:
        raise serializers.ValidationError(f"Invalid Google token: {e}")
    
    return info

