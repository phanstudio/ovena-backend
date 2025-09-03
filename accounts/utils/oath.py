from django.conf import settings
import requests

def exchange_code_for_tokens(provider: str, code: str, code_verifier: str = None):
    cfg = settings.OAUTH_PROVIDERS.get(provider)
    if not cfg:
        raise ValueError("Unknown provider")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": cfg.get("CLIENT_ID"),
        "redirect_uri": cfg.get("REDIRECT_URI"),
    }
    if provider == "google":
        # For PKCE, also send code_verifier
        if code_verifier:
            data["code_verifier"] = code_verifier
        # don't send client_secret if using PKCE on mobile; but server-side can include it if configured
        # Here we include client_secret because token exchange is done from backend securely
        data["client_secret"] = cfg.get("CLIENT_SECRET")
        resp = requests.post(cfg.get("TOKEN_ENDPOINT"), data=data, timeout=10)
        resp.raise_for_status()
        return resp.json()

    elif provider == "apple":
        # Apple expects client_secret (JWT) and other fields
        data["client_secret"] = cfg.get("CLIENT_SECRET")
        data["client_id"] = cfg.get("CLIENT_ID")
        resp = requests.post(cfg.get("TOKEN_ENDPOINT"), data=data, timeout=10)
        resp.raise_for_status()
        return resp.json()

    else:
        raise ValueError("Provider not implemented")

def fetch_userinfo(provider: str, access_token: str):
    cfg = settings.OAUTH_PROVIDERS.get(provider)
    if provider == "google":
        resp = requests.get(cfg.get("USERINFO_ENDPOINT"), headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
        resp.raise_for_status()
        return resp.json()
    elif provider == "apple":
        # Apple returns id_token (JWT) containing user info; parse it instead of a userinfo endpoint
        # We'll return the token data and let the caller decode it.
        return {"id_token": access_token}
    return {}
