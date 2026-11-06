from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework.permissions import IsAuthenticated
from accounts.serializers import InS
from authflow.services.jwt import (
    issue_jwt_for_user_with_plan,
    issue_jwt_for_user,
    refresh_jwt_tokens,
)
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from django.contrib.auth import get_user_model

User = get_user_model()



class RefreshTokenView(APIView):
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"error": "Refresh token required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tokens = refresh_jwt_tokens(refresh_token)
            return Response(tokens, status=status.HTTP_200_OK)
        except (TokenError, AuthenticationFailed) as e:
            return Response({"error": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_401_UNAUTHORIZED)


class RotateTokenView(APIView):
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"error": "Refresh token required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tokens = refresh_jwt_tokens(refresh_token)
            return Response(tokens, status=status.HTTP_200_OK)
        except (TokenError, AuthenticationFailed) as e:
            return Response({"error": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(GenericAPIView):
    serializer_class = InS.LogoutSerializer
    # permission_classes = [IsAuthenticated] not sure if we need is authenticated
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        try:
            token = RefreshToken(vd["refresh"])
            # if str(token["user_id"]) != str(request.user.id):
            #     return Response({"error": "Token mismatch"}, status=400)
            token.blacklist()
        except Exception as e:
            print(f"error: Invalid token: {e}")
    
        return Response({"message": "Logged out"})

# DEV ONLY: For local/testing fixtures only, not exposed to customers in production
class LogInView(APIView):

    def post(self, request):
        phone_number = request.data.get("phone_number")
        email = request.data.get("email")

        if not phone_number and not email:
            return Response({"error": "Phone number or email is required"}, status=400)

        user = None
        if phone_number:
            # ✅ Create or get the user
            user = User.objects.filter(phone_number=phone_number).first()
        else:
            user = User.objects.filter(email=email).first()
      
        if not user:
            return Response({"error": f"User does not exist for: {phone_number if phone_number else email}"}, status=400)

        # ✅ Issue JWT tokens
        token = issue_jwt_for_user(user)
        return Response({
            "message": "User logged in successfully",
            "refresh": token["refresh"],
            "access": token["access"],
        }, status=200)

class Health(APIView):
    def get(self, _request):
        return Response({"message": "healthy"}, status=200)
