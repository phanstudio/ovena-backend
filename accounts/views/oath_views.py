from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from accounts.serializers import UserSerializer, OAuthCodeSerializer
# from accounts.models import User
from ..utils.oath import verify_apple_token
from authflow.services import issue_jwt_for_user
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
        # info["referre_code"] = request.data.get('referre_code')
        # info["lat"] = request.data.get('lat')
        # info["long"] = request.data.get('long')

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
        vd = s.validated_data
        provider = vd["provider"]
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
        
        if isinstance(info, dict):
            info.update({k: v for k, v in vd.items() if k not in ("provider", "id_token")})
            print(info)
        
        if user:
            pass # raise error

        print(user, info)
        # send there location
        if info["created"]:
            data:dict = {
                # "long": info.get("long"),
                # "lat": info.get("lat"),
                # "birth_date": info.get("birth_date"),
                # "name": f"{info.get('given_name','')} {info.get('family_name','')}".strip(),
                # "referre_code": info.get("referre_code"),
                # "phone_number": info.get("phone_number"),
            }
            mainname:str = f"{info.get('given_name','')} {info.get('family_name','')}".strip()
            data.update(info)
            # {k: v for k, v in vd.items() if k not in ("provider", "id_token")}
            # jl = data.copy()
            # jl.update({k: v for k, v in info.items() if k not in ("given_name", "family_name")})
            # print(jl)
            
            if mainname.replace(" ", "") != "":
                data["name"] = mainname
            # picture info["picture"]
            serializer = CreateCustomerSerializer(
                data=data,
                context={"user": user}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

        # this might be a probelm we might ask for the refresh token to destroy or create a  access if that process is not done
        tokens = issue_jwt_for_user(user) 
        
        return Response({
            "user": UserSerializer(user).data,
            "tokens": tokens,
            "message": "OAUTH User creation successfully",
            # "refresh": token["refresh"],
            # "access": token["access"],
            "is_new_user": info["created"]
        })
