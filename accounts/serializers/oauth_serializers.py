from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()

# ─────────────────────────────────────────────────────────────
# OAuth entry serializers
# ─────────────────────────────────────────────────────────────

class OAuthCodeSerializer(serializers.Serializer):
    """
    Top-level dispatcher payload. `provider` picks the branch in
    OAuthExchangeView; everything else is provider-specific and validated
    by the nested serializers below inside AuthLogic.
    """
    provider = serializers.ChoiceField(choices=["google", "apple"])


class GoogleAuthSerializer(serializers.Serializer):
    """
    Unchanged from what you had — Google's id_token verification already
    worked. Included here for completeness / so the whole auth surface
    is in one place.
    """
    id_token = serializers.CharField()

    def validate(self, data):
        # Wherever your existing Google verification call lives — keeping
        # the interface the same: returns {"info": {...claims...}}
        from accounts.utils.oath import verify_google_token  # your existing util

        info = verify_google_token(data["id_token"])
        return {"info": info}


class AppleNameSerializer(serializers.Serializer):
    """
    Apple sends this only on the user's very first authorization, as a
    separate JSON object alongside the identity token — never inside the
    JWT, never again on repeat logins. Must be optional.
    """
    firstName = serializers.CharField(required=False, allow_blank=True)
    lastName = serializers.CharField(required=False, allow_blank=True)


class AppleAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField()
    authorization_code = serializers.CharField(required=False, allow_blank=True)
    # First-login-only payload from Apple's native SDK. Frontend should
    # send this whenever it has it (i.e. right after the native Apple
    # sign-in call) and omit it on subsequent logins where Apple doesn't
    # supply it anymore.
    user = AppleNameSerializer(required=False)
