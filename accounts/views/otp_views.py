from rest_framework.views import APIView
from rest_framework.response import Response
from ..utils.otp import send_otp, verify_otp
from authflow.services import _issue_jwt_for_user
from django.contrib.auth import get_user_model

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

        if not phone_number or not otp_code:
            return Response({"error": "Phone number and OTP are required"}, status=400)

        if not verify_otp(phone_number, otp_code):
            return Response({"error": "Invalid or expired OTP"}, status=400)

        # ✅ Create or get the user
        user, created = User.objects.get_or_create(
            phone_number=phone_number,
            defaults={"phone_number": phone_number}
        )

        # ✅ Issue JWT tokens
        token = _issue_jwt_for_user(user)
        return Response({
            "message": "OTP verified successfully",
            "refresh": token["refresh"],
            "access": token["access"],
            "is_new_user": created
        }, status=200)
