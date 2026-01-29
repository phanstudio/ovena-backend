from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from accounts.serializers import UserSerializer, OAuthCodeSerializer
from accounts.models import User
from ..utils.oath import verify_apple_token
from authflow.services import _issue_jwt_for_user
from django.contrib.auth import get_user_model
from ..serializers import GoogleAuthSerializer, CreateCustomerSerializer
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
        info["referre_code"] = serializer.validated_data['referre_code']
        info["lat"] = serializer.validated_data['lat']
        info["long"] = serializer.validated_data['long']

        user, info["created"] = User.objects.get_or_create(
            email=serializer.validated_data['email'],
            defaults={'email': serializer.validated_data['email']}
        )
        
        return {"user": user, "info": info}
    
    @staticmethod
    def apple(request):
        token = request.data.get("id_token")
        payload = verify_apple_token(token)

        email = payload.get("email")
        apple_id = payload["sub"]

        print(payload)
        info = {apple_id}
        info["referre_code"] = request.data.get("referre_code")
        info["lat"] = request.data.get("lat")
        info["long"] = request.data.get("long")

        user, info["created"] = User.objects.get_or_create(
            email=email,
            defaults={'email': email}
        )
        
        return {"user": user, "info": info}

class OAuthExchangeView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        s = OAuthCodeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        provider = s.validated_data["provider"]
        # we will need refrred by 
        user = None
        info = None

        match provider:
            case "google":
                user_data = AuthLogic.google(request)
                user = user_data["user"]
                info = user_data["info"]
            case "apple":
                user_data = AuthLogic.apple(request)
                user = user_data["user"]
                info = user_data["info"]
            case _:
                return Response({
                    "detail": "provider should be google or apple", "error": "provider invalid"},
                      status=status.HTTP_400_BAD_REQUEST)
        
        if user:
            pass # raise error

        # send there location
        if info["created"]:
            data = {
                # "email": info["email"],
                "long": info["long"],
                "lat": info["lat"],
                # "birth_date": "april 2000 22",
                "name": f"{info["given_name"]} {info["family_name"]}",
                "referre_code": info["referre_code"]
            }
            # picture info["picture"]
            serializer = CreateCustomerSerializer(
                data=data,
                context={"user": user}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

        # this might be a probelm we might ask for the refresh token to destroy or create a  access if that process is not done
        tokens = _issue_jwt_for_user(user) 
        
        return Response({
            "user": UserSerializer(user).data,
            "tokens": tokens,
            "message": "OAUTH User creation successfully",
            # "refresh": token["refresh"],
            # "access": token["access"],
            "is_new_user": info["created"]
        })
