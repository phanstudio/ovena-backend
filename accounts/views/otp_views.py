from rest_framework.views import APIView
from rest_framework.response import Response
from ..utils.otp import send_otp, verify_otp
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import (
    CustomerProfile, #DriverProfile, RestaurantProfile
)

User = get_user_model()
class SendOTPView(APIView):
    def post(self, request):
        phone_number = request.data.get("phone_number")
        if not phone_number:
            return Response({"error": "Phone number is required"}, status=400)

        result = send_otp(phone_number)
        return Response(result, status=200)

class VerifyOTPView(APIView):
    """
    Verifies OTP, creates user if not exists, and returns JWT tokens
    """
    def post(self, request):
        phone_number = request.data.get("phone_number")
        otp_code = request.data.get("otp_code")
        location = request.data.get("location", "lagos, ikeja")
        name = request.data.get("name", "Unknown")
        # role = request.data.get("role", "customer")  # optional, default customer

        if not phone_number or not otp_code:
            return Response({"error": "Phone number and OTP are required"}, status=400)

        if not verify_otp(phone_number, otp_code):
            return Response({"error": "Invalid or expired OTP"}, status=400)

        # ✅ Create or get the user
        user, created = User.objects.get_or_create(
            phone_number=phone_number,
            defaults={"phone_number": phone_number, "role": "customer", "name": name}  # or any default fields
        )
        if created:
            CustomerProfile.objects.create(user=user, location=location)

        # ✅ Issue JWT tokens
        refresh = RefreshToken.for_user(user)
        return Response({
            "message": "OTP verified successfully",
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "is_new_user": created
        }, status=200)
