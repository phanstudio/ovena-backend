from django.conf import settings
import jwt
import requests
from jwt.algorithms import RSAAlgorithm

APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"

def verify_apple_token(token):
    keys = requests.get(APPLE_KEYS_URL, timeout=120).json()['keys']
    header = jwt.get_unverified_header(token)

    key = next(k for k in keys if k['kid'] == header['kid'])
    public_key = RSAAlgorithm.from_jwk(key)

    payload = jwt.decode(
        token,
        public_key,
        audience=settings.APPLE_SERVICE_ID,
        issuer="https://appleid.apple.com",
        algorithms=["RS256"]
    )
    return payload
