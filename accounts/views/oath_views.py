from rest_framework.response import Response
from rest_framework import status, permissions
from accounts.serializers import OAuthCodeSerializer
from ..utils.oath import verify_apple_token
from authflow.services import issue_jwt_for_user
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import ValidationError
from accounts.serializers import GoogleAuthSerializer, CreateCustomerSerializer
from rest_framework.generics import GenericAPIView
from drf_spectacular.utils import extend_schema, inline_serializer # type: ignore
from rest_framework import serializers as s

User = get_user_model()

class AuthLogic():
    @staticmethod
    def google(request):
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # If still no email, you can fallback to using provider-sub as unique id and store in a field
        #     external_id = f"{provider}:{sub}"

        # what is sub for
        info = serializer.validated_data['info']
        mainname:str = f"{info.get('given_name','')} {info.get('family_name','')}".strip()
        data = {
            'email': info['email']
        }
        
        if mainname != "":
            data["name"] = mainname
        
        user, info["created"] = User.objects.get_or_create(
            email=info['email'],
            defaults=data
        )
        
        return (user, info)
    
    @staticmethod
    def apple(request):
        token = request.data.get("id_token")
        payload = verify_apple_token(token)

        email = payload.get("email")
        apple_id = payload["sub"]

        print(payload)
        info = {"sub": apple_id}
        # info = {apple_id}
        user, info["created"] = User.objects.get_or_create(
            email=email,
            defaults={'email': email}
        )
        
        return (user, info)

@extend_schema(
    responses={201: inline_serializer("Phase2Response", fields={
        "message": s.CharField(),
        "is_new_user": s.BooleanField(),
        "refresh": s.CharField(),
        "access": s.CharField(),
    })}
)
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
        info = None

        match provider:
            case "google":
                user, info = AuthLogic.google(request)
            case "apple":
                user, info = AuthLogic.apple(request)
            case _:
                return Response({
                    "detail": "provider should be google or apple", "error": "provider invalid"},
                      status=status.HTTP_400_BAD_REQUEST)
        
        if not isinstance(info, dict):
            raise ValidationError("Invalid OAuth response")

        # this might be a probelm we might ask for the refresh token to 
        # destroy or create a access if that process is not done
        token = issue_jwt_for_user(user) 
        return Response({
            "refresh": token["refresh"],
            "access": token["access"],
            "message": "OAUTH User creation successfully",
            "is_new_user": info["created"]
        })
