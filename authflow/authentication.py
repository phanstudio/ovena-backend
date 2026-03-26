import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication as SimpleJWTAuth
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password
from accounts.models import LinkedStaff
from accounts.services.roles import has_role
from accounts.services.profiles import (
    PROFILE_BUSINESS_ADMIN,
    PROFILE_CUSTOMER,
    PROFILE_DRIVER,
    PROFILE_BUSINESS_STAFF,
    # get_profile,
    resolve_active_profile_type,
    apply_profile_fetches,
)

def _prime_profile_cache_from_prefetch(user):
    """
    Requires: user queryset had .prefetch_related("profile_bases__customer_profile", "profile_bases__driver_profile")
    """
    from accounts.services.profiles import _profile_cache
    cache = _profile_cache(user)
    
    for base in user.profile_bases.all():  # hits prefetch cache, no query
        pt = base.profile_type
        if pt == PROFILE_CUSTOMER:
            cache[pt] = getattr(base, "customer_profile", None)
        elif pt == PROFILE_DRIVER:
            cache[pt] = getattr(base, "driver_profile", None)

    # business_admin and primaryagent still come from select_related
    try:
        cache[PROFILE_BUSINESS_ADMIN] = user.business_admin
    except Exception:
        cache[PROFILE_BUSINESS_ADMIN] = None

    try:
        cache[PROFILE_BUSINESS_STAFF] = user.primaryagent
    except Exception:
        cache[PROFILE_BUSINESS_STAFF] = None

def _prime_profile_cache(user):
    """
    After select_related has already loaded related objects,
    populate the profile cache so permissions never hit the DB.
    """
    from accounts.services.profiles import _profile_cache

    cache = _profile_cache(user)

    # These were loaded via select_related — no extra query
    try:
        cache[PROFILE_BUSINESS_ADMIN] = user.business_admin
    except Exception:
        cache[PROFILE_BUSINESS_ADMIN] = None

    try:
        cache[PROFILE_BUSINESS_STAFF] = user.primaryagent
    except Exception:
        cache[PROFILE_BUSINESS_STAFF] = None
    
    _prime_profile_cache_from_prefetch(user)

    # Customer/Driver need ProfileBase queries — only pre-warm if you
    # did a prefetch_related("profilebase_set") on the queryset.
    # Otherwise leave them uncached; they'll lazy-load once and cache.

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
        qs = apply_profile_fetches(
            self.user_model.objects.all(),
            self.allowed_profile_types(),
        )
        return qs.get(**{api_settings.USER_ID_FIELD: user_id})

    def allowed_profile_types(self):
        return []

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
        
        if api_settings.CHECK_REVOKE_TOKEN: # i migth have to change to match?
            if validated_token.get(
                api_settings.REVOKE_TOKEN_CLAIM
            ) != get_md5_hash_password(user.password):
                raise AuthenticationFailed(
                    _("The user's password has been changed."), code="password_changed"
                )

        return user

    def custom_auth(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result

        _prime_profile_cache(user)

        active_profile = resolve_active_profile_type(
            request=request,
            user=user,
            allowed_types=self.allowed_profile_types(),
        )

        return (user, token, active_profile)


class CustomprimJWTAuth(CustomJWtAuth):
    def allowed_profile_types(self):
        return [PROFILE_BUSINESS_ADMIN, PROFILE_BUSINESS_STAFF]
    
    def authenticate(self, request):
        result = super().custom_auth(request)

        if result is None:
            return None
        user, token, active_profile = result

        if active_profile:
            token["active_profile"] = active_profile

        if getattr(user, "primaryagent", None) is not None:
            token["scopes"] = {"*"}
        return (user, token)

class CustomDriverAuth(CustomJWtAuth):
    def allowed_profile_types(self):
        return [PROFILE_DRIVER]

    def authenticate(self, request):
        result = super().custom_auth(request)
        if result is None:
            return None
        user, token, profile_type = result
        if profile_type:
            token["active_profile"] = profile_type
        return (user, token)

class CustomCustomerAuth(CustomJWtAuth):
    def allowed_profile_types(self):
        return [PROFILE_CUSTOMER]

    def authenticate(self, request):
        result = super().custom_auth(request)
        if result is None:
            return None
        user, token, profile_type = result
        if profile_type:
            token["active_profile"] = profile_type
        return (user, token)

class CustomBAdminAuth(CustomJWtAuth):
    def allowed_profile_types(self):
        return [PROFILE_BUSINESS_ADMIN]
    
    def authenticate(self, request):
        # result = super().authenticate(request)
        # if result is None:
        #     return None
        # user, token = result
        # _prime_profile_cache(user)
        # profile_type = resolve_active_profile_type(
        #     request=request,
        #     user=user,
        #     allowed_types=self.allowed_profile_types(),
        # )
        result = super().custom_auth(request)
        if result is None:
            return None
        user, token, profile_type = result
        if not profile_type:
            raise AuthenticationFailed(_("Business admin profile not found"), code="business_admin_missing")
        token["active_profile"] = profile_type
        return (user, token)
# we need test cases for the authentication
