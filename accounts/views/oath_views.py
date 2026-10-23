from rest_framework.response import Response
from rest_framework import status, permissions
from accounts.serializers.oauth_serializers import (
    OAuthCodeSerializer,
    GoogleAuthSerializer,
    AppleAuthSerializer,
)
from ..utils.oath import verify_apple_token
from authflow.services.jwt import issue_jwt_for_user, issue_jwt_for_user_with_plan
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.generics import GenericAPIView
from accounts.models import SocialAccount
from accounts.services.profiles import PROFILE_CUSTOMER

User = get_user_model()


class AuthLogic:
    @staticmethod
    def _get_or_link_user(provider, sub, email, defaults=None, raw_signup=None):
        social = SocialAccount.objects.filter(
            provider=provider, provider_uid=sub
        ).select_related("user").first()

        if social:
            return social.user, False

        user = None
        if email:
            user = User.objects.filter(email=email).first()

        created = False
        if not user:
            user = User.objects.create(email=email, **(defaults or {}))
            created = True

        SocialAccount.objects.create(
            user=user,
            provider=provider,
            provider_uid=sub,
            email_at_signup=email,
            raw_signup_payload=raw_signup,
        )
        return user, created

    @staticmethod
    def google(request):
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        info = serializer.validated_data["info"]

        user, created = AuthLogic._get_or_link_user(
            provider=SocialAccount.PROVIDER_GOOGLE,
            sub=info["sub"],
            email=info.get("email"),
            raw_signup=info,
        )
        mainname: str = f"{info.get('given_name','')} {info.get('family_name','')}".strip()
        prefill = {
            "name": mainname or None,
            "email": info.get("email"),
            "profile_pic": info.get("picture"),
        }
        return user, created, prefill

    @staticmethod
    def apple(request):
        serializer = AppleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        payload = verify_apple_token(vd["id_token"])
        email = payload.get("email")

        # Apple only sends user name on the first authorization
        name = None
        user_info = vd.get("user") or request.data.get("name")
        if isinstance(user_info, dict):
            first = user_info.get("firstName") or user_info.get("givenName") or ""
            last = user_info.get("lastName") or user_info.get("familyName") or ""
            name = f"{first} {last}".strip() or None

        raw_signup = {"name": name, "email": email} if (name or email) else None

        user, created = AuthLogic._get_or_link_user(
            provider=SocialAccount.PROVIDER_APPLE,
            sub=payload["sub"],
            email=email,
            raw_signup=raw_signup,
        )

        # If returning user didn't send name (Apple never resends it), recover from saved raw_signup_payload
        if not name and not created:
            social = SocialAccount.objects.filter(
                provider=SocialAccount.PROVIDER_APPLE, provider_uid=payload["sub"]
            ).first()
            if social and social.raw_signup_payload:
                name = social.raw_signup_payload.get("name")
                if not email:
                    email = social.raw_signup_payload.get("email")

        prefill = {"name": name or None, "email": email or user.email, "profile_pic": None}  # Apple never provides an avatar
        return user, created, prefill


class OAuthExchangeView(GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = OAuthCodeSerializer

    @transaction.atomic
    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        vd = s.validated_data
        provider = vd["provider"]
        # we will need refrred by 
        user = None

        match provider:
            case "google":
                user, created, prefill = AuthLogic.google(request)
            case "apple":
                user, created, prefill = AuthLogic.apple(request)
            case _:
                return Response({
                    "detail": "provider should be google or apple", "error": "provider invalid"},
                      status=status.HTTP_400_BAD_REQUEST)

        needs_registration = not bool(getattr(user, "customer_profile", None))
        if needs_registration:
            token = issue_jwt_for_user(user)
        else:
            token = issue_jwt_for_user_with_plan(user, active_profile=PROFILE_CUSTOMER)

        return Response({
            "refresh": token["refresh"],
            "access": token["access"],
            "is_new_user": created,
            "needs_registration": needs_registration,
            "provider": provider,
            "prefill": prefill,  # {"name": ..., "email": ..., "profile_pic": ...} or {}
        })
