import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication as SimpleJWTAuth
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password
from accounts.models import LinkedStaff

# add login mechanics also consider when to perfom the login on evry reuest or on every session and whta is a sesion considered
class CustomJWTAuthentication(BaseAuthentication): # any way to speed this up
    """
    Supports both:
    - Main user tokens (SimpleJWT) → "Authorization: Bearer <token>"
    - Sub user tokens (custom)     → "Authorization: SubBearer <token>"
    """

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return None

        if auth_header.startswith("Bearer "):
            # Delegate to SimpleJWT for normal tokens
            simple_jwt = CustomprimJWTAuth()
            return simple_jwt.authenticate(request)

        elif auth_header.startswith("SubBearer "):
            token = auth_header[len("SubBearer "):]

            try: 
                payload = jwt.decode(
                    token,
                    settings.SECRET_KEY,
                    algorithms=["HS256"],
                ) # a way to destroy just this stoken incase of early teminaton that is still fast problem for later
            except jwt.ExpiredSignatureError:
                raise AuthenticationFailed("Sub token expired")
            except jwt.InvalidTokenError:
                raise AuthenticationFailed("Invalid sub token")

            account = (
                LinkedStaff.objects
                .select_related("created_by", "created_by__branch")#, "created_by__user")
                .filter(device_name=payload["device_id"])
                .first()
            )
            # change to device id
            if not account:
                raise AuthenticationFailed("Account not found")
            if account.revoked:
                raise AuthenticationFailed("Account revoked")

            auth_data = {
                "token_type": "sub", # nosec B105
                "scopes": set(payload.get("scopes", [])),
                "device_id": payload.get("device_id"), # optional extra 
                # also we need to record the person login in like a side efect that should not affect flow speed
            }

            return (account, auth_data)

        return None

# doesn't password vary depending on the settings??
class CustomJWtAuth(SimpleJWTAuth):
    def custom_get_user(self, user_id):
        return self.user_model.objects.get(
                **{api_settings.USER_ID_FIELD: user_id}
            )

    def get_user(self, validated_token):
        """
        Return user with primaryagent preloaded for efficiency.
        """
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError:
            raise InvalidToken(_("Token contained no recognizable user identification"))

        try:
            user = self.custom_get_user(user_id)
        except self.user_model.DoesNotExist:
            raise AuthenticationFailed(_("User not found"), code="user_not_found")

        if api_settings.CHECK_USER_IS_ACTIVE and not user.is_active:
            raise AuthenticationFailed(_("User is inactive"), code="user_inactive")
        
        if api_settings.CHECK_REVOKE_TOKEN:
            if validated_token.get(
                api_settings.REVOKE_TOKEN_CLAIM
            ) != get_md5_hash_password(user.password):
                raise AuthenticationFailed(
                    _("The user's password has been changed."), code="password_changed"
                )

        return user

class CustomprimJWTAuth(CustomJWtAuth):
    def custom_get_user(self, user_id):
        return self.user_model.objects.select_related("primaryagent", "primaryagent__branch").get(
                **{api_settings.USER_ID_FIELD: user_id}
            )
    
    def authenticate(self, request):
        user, token =  super().authenticate(request)
        # token["is_manager"] = (
        #     getattr(user, "role", None) == "restaurantstaff" and
        #     user.primaryagent is not None
        # )
        if (getattr(user, "role", None) == "restaurantstaff" and
                user.primaryagent is not None
            ):
            token["scopes"] = {"*"}
        return (user, token)

class CustomDriverAuth(CustomJWtAuth):
    def custom_get_user(self, user_id):
        return self.user_model.objects.select_related("driver_profile").get(
            **{api_settings.USER_ID_FIELD: user_id}
        )

class CustomCustomerAuth(CustomJWtAuth):
    def custom_get_user(self, user_id):
        return self.user_model.objects.select_related("customer_profile").get(
            **{api_settings.USER_ID_FIELD: user_id}
        )

class CustomBAdminAuth(CustomJWtAuth):
    def custom_get_user(self, user_id):
        return self.user_model.objects.select_related("business_admin").get(
            **{api_settings.USER_ID_FIELD: user_id}
        )
