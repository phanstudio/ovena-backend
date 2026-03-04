from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from accounts.serializers import UserSerializer, OAuthCodeSerializer
from ..utils.oath import verify_apple_token
from authflow.services import issue_jwt_for_user
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import ValidationError
from accounts.serializers import GoogleAuthSerializer, CreateCustomerSerializer
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
        user, info["created"] = User.objects.get_or_create(
            email=info['email'],
            defaults={'email': info['email']}
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

class OAuthExchangeView(APIView):
    permission_classes = [permissions.AllowAny]

    @transaction.atomic
    def post(self, request):
        s = OAuthCodeSerializer(data=request.data)
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
        info = {**info, **vd}

        # send there location
        if info["created"]:
            mainname:str = f"{info.get('given_name','')} {info.get('family_name','')}".strip()
            allowed_fields = {
                # "given_name",
                # "family_name",
                "picture",
                "phone_number",
                "referre_code",
                "birth_date",
                "lat",
                "long",
            }

            data:dict = {k: v for k, v in info.items() if k in allowed_fields}

            # jl = data.copy()
            # jl.update({k: v for k, v in info.items() if k not in ("given_name", "family_name")})
            # print(jl)
            
            if mainname.strip() != "":
                data["name"] = mainname
            print(data)

            # picture info["picture"]
            serializer = CreateCustomerSerializer(
                data=data,
                context={"user": user}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

        # this might be a probelm we might ask for the refresh token to 
        # destroy or create a access if that process is not done
        tokens = issue_jwt_for_user(user) 
        return Response({
            "user": UserSerializer(user).data,
            "tokens": tokens,
            "message": "OAUTH User creation successfully",
            "is_new_user": info["created"]
        })
