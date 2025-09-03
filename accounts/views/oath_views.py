from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from accounts.serializers import UserSerializer, OAuthCodeSerializer
# from .services import exchange_code_for_tokens, fetch_userinfo
from accounts.models import User
import jwt
from ..utils.oath import exchange_code_for_tokens, fetch_userinfo
from ..utils.token_service import _issue_jwt_for_user

class OAuthExchangeView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        s = OAuthCodeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        provider = s.validated_data["provider"]
        code = s.validated_data["code"]
        code_verifier = s.validated_data.get("code_verifier")

        # Exchange code for tokens with provider
        try:
            token_response = exchange_code_for_tokens(provider, code, code_verifier)
        except Exception as e:
            return Response({"detail": "Token exchange failed", "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Extract access_token / id_token
        access_token = token_response.get("access_token")
        id_token = token_response.get("id_token")

        # Get user info
        try:
            userinfo = fetch_userinfo(provider, access_token or id_token)
        except Exception as e:
            return Response({"detail": "Fetching userinfo failed", "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        print(userinfo)
        # Map provider info to local user
        email = userinfo.get("email") or None
        name = userinfo.get("name") or userinfo.get("given_name") or ""
        sub = userinfo.get("sub") or None

        # For Apple, the email is inside the id_token; ensure you decode id_token if needed
        if provider == "apple" and id_token and not email:
            try:
                decoded = jwt.decode(id_token, options={"verify_signature": False})
                email = decoded.get("email")
                sub = decoded.get("sub")
            except Exception:
                pass

        if not email:
            # If still no email, you can fallback to using provider-sub as unique id and store in a field
            external_id = f"{provider}:{sub}"
            user, _ = User.objects.get_or_create(email=None, defaults={"name": name})
        else:
            user, _ = User.objects.get_or_create(email=email, defaults={"name": name})

        tokens = _issue_jwt_for_user(user)
        return Response({"user": UserSerializer(user).data, "tokens": tokens})

# class ProfileView(APIView):
#     permission_classes = [permissions.IsAuthenticated]

#     def get(self, request):
#         return Response(UserSerializer(request.user).data)