from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from accounts.serializers import UserSerializer, OAuthCodeSerializer
from accounts.models import User
import jwt
from ..utils.oath import exchange_code_for_tokens, fetch_userinfo
from authflow.services import _issue_jwt_for_user
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from ..serializers import GoogleAuthSerializer, CreateCustomerSerializer
User = get_user_model()


# class OAuthExchangeView(APIView):
#     permission_classes = [permissions.AllowAny]

#     def post(self, request):
#         s = OAuthCodeSerializer(data=request.data)
#         s.is_valid(raise_exception=True)
#         provider = s.validated_data["provider"]
#         code = s.validated_data["code"]
#         code_verifier = s.validated_data.get("code_verifier")

#         # Exchange code for tokens with provider
#         try:
#             token_response = exchange_code_for_tokens(provider, code, code_verifier)
#         except Exception as e:
#             return Response({"detail": "Token exchange failed", "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

#         # Extract access_token / id_token
#         access_token = token_response.get("access_token")
#         id_token = token_response.get("id_token")

#         # Get user info
#         try:
#             userinfo = fetch_userinfo(provider, access_token or id_token)
#         except Exception as e:
#             return Response({"detail": "Fetching userinfo failed", "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
#         print(userinfo)
#         # Map provider info to local user
#         email = userinfo.get("email") or None
#         name = userinfo.get("name") or userinfo.get("given_name") or ""
#         sub = userinfo.get("sub") or None

#         # For Apple, the email is inside the id_token; ensure you decode id_token if needed
#         if provider == "apple" and id_token and not email:
#             try:
#                 decoded = jwt.decode(id_token, options={"verify_signature": False})
#                 email = decoded.get("email")
#                 sub = decoded.get("sub")
#             except Exception:
#                 pass

#         if not email:
#             # If still no email, you can fallback to using provider-sub as unique id and store in a field
#             external_id = f"{provider}:{sub}"
#             user, _ = User.objects.get_or_create(email=None, defaults={"name": name})
#         else:
#             user, _ = User.objects.get_or_create(email=email, defaults={"name": name})

#         tokens = _issue_jwt_for_user(user)
#         return Response({"user": UserSerializer(user).data, "tokens": tokens})


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
            email=serializer.validated_data['email'],
            defaults={'email': serializer.validated_data['email']}
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
                ...
            case _:
                return Response({
                    "detail": "provider should be google or apple", "error": "provider invalid"},
                      status=status.HTTP_400_BAD_REQUEST)
        
        if user:
            pass # raise error

        # send there location 
        # "referre_code": "476839039"
        if info["created"]:
            data = {
                # "email": info["email"],
                # "long": 678.9,
                # "lat": 678.9,
                # "birth_date": "april 2000 22",
                "name": f"{info["given_name"]} {info["family_name"]}",
                # "referre_code": "476839039"
            }
            # picture info["picture"]
            serializer = CreateCustomerSerializer(
                data=data,
                context={"user": user}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

        tokens = _issue_jwt_for_user(user)
        return Response({"user": UserSerializer(user).data, "tokens": tokens})
