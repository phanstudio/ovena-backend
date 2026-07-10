from rest_framework.response import Response
from rest_framework import status, permissions
from accounts.serializers import OAuthCodeSerializer
from ..utils.oath import verify_apple_token
from authflow.services.jwt import issue_jwt_for_user, issue_jwt_for_user_with_plan
from django.contrib.auth import get_user_model
from django.db import transaction
from accounts.serializers.oauth_serializers import GoogleAuthSerializer, AppleAuthSerializer
from rest_framework.generics import GenericAPIView
from accounts.models import SocialAccount
from accounts.services.profiles import PROFILE_CUSTOMER

User = get_user_model()

# one flaw with this s the fact that 2 people can have hte same email; 
# second is we can check for cutomer profile or and etra profile for it to verify
class AuthLogic:
    @staticmethod
    def _get_or_link_user(provider, sub, email, defaults=None):
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
            user=user, provider=provider, provider_uid=sub, email_at_signup=email
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
        )
        mainname:str = f"{info.get('given_name','')} {info.get('family_name','')}".strip()
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

        user, created = AuthLogic._get_or_link_user(
            provider=SocialAccount.PROVIDER_APPLE,
            sub=payload["sub"],
            email=email,
        )
        name = None
        if vd.get("name"): # this should be user
            name = f"{vd['name'].get('firstName','')} {vd['name'].get('lastName','')}".strip()

        prefill = {"name": name or None, "email": email, "profile_pic": None}  # apple never gives a pic
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

        needs_registration = not bool(user.customer_profile)
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
