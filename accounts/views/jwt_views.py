from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from authflow.services import _issue_jwt_for_user
from django.contrib.auth import get_user_model

User = get_user_model()

class RefreshTokenView(APIView):
    def post(self, request):
        refresh_token = request.data.get("refresh")

        try:
            refresh = RefreshToken(refresh_token)

            return Response({
                "access": str(refresh.access_token),
                "refresh": refresh_token  # same one
            })

        except TokenError:
            return Response({"error": "Invalid or expired refresh"}, status=401)

class RotateTokenView(APIView):
    def post(self, request):
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            return Response({"error": "Refresh token required"}, status=400)

        try:
            refresh = RefreshToken(refresh_token)

            # ⚠️ THIS INVALIDATES THE OLD REFRESH
            new_refresh = refresh.rotate()

            return Response({
                "access": str(new_refresh.access_token),
                "refresh": str(new_refresh)
            }, status=200)

        except TokenError:
            return Response(
                {"error": "Invalid or expired refresh token"},
                status=status.HTTP_401_UNAUTHORIZED
            )

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"message": "Logged out"})
        except Exception:
            return Response({"error": "Invalid token"}, status=400)

class LogInView(APIView):
    # permission_classes = [IsAuthenticated]

    def post(self, request):
        phone_number = request.data.get("phone_number")
        email = request.data.get("email")

        if not phone_number and not email:
            return Response({"error": "Phone number or email is required"}, status=400)


        if phone_number:
            # ✅ Create or get the user
            user = User.objects.get(
                phone_number=phone_number,
            )
        else:
            user = User.objects.get(
                email=email,
            )

        # ✅ Issue JWT tokens
        token = _issue_jwt_for_user(user)
        return Response({
            "message": "User logged in successfully",
            "refresh": token["refresh"],
            "access": token["access"],
        }, status=200)

