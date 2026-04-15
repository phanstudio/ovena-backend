from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from accounts.serializers import InS
from authflow.services import issue_jwt_for_user
from django.contrib.auth import get_user_model

User = get_user_model()
# rate limit instead of block
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

class LogoutView(GenericAPIView):
    serializer_class = InS.LogoutSerializer
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        try:
            token = RefreshToken(vd["refresh"])
            if str(token["user_id"]) != str(request.user.id):
                return Response({"error": "Token mismatch"}, status=400)
            token.blacklist()
        except Exception as e:
            print(f"error: Invalid token: {e}")
    
        return Response({"message": "Logged out"})

class LogInView(APIView): # can work with password, will be removed

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
