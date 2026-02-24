from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
# from ..utils.otp import send_otp, verify_otp
from authflow.services import issue_jwt_for_user, request_email_otp, request_phone_otp, verify, OTPInvalidError
from django.contrib.auth import get_user_model
# from .account_views import RegisterCustomerSerializer

# do we have dedcted endpoints for sending otp for the admin registration since it still send the otp forward.

User = get_user_model()
class SendPhoneOTPView(APIView):
    def post(self, request):
        phone_number = request.data.get("phone_number")
        return request_phone_otp(phone_number)

class SendEmailOTPView(APIView):
    def post(self, request):
        email = request.data.get("email")
        return request_email_otp(email)

class VerifyOTPView(APIView): # we need to revoke the jwt also use the refresh to get the new access, also the getting new refresh token
    """
    Verifies OTP, creates user if not exists, and returns JWT tokens
    """
    def post(self, request):
        phone_number = request.data.get("phone_number")
        otp_code = request.data.get("otp_code")

        if not phone_number or not otp_code:
            return Response({"error": "Phone number and OTP are required"}, status=status.HTTP_400_BAD_REQUEST)
        
        identifier = ""
        try:
            identifier = verify(otp_code, phone_number)
        except OTPInvalidError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)        

        # ✅ Create or get the user
        user, created = User.objects.get_or_create(
            phone_number=identifier,
            defaults={"phone_number": identifier}
        )

        # ✅ Issue JWT tokens
        token = issue_jwt_for_user(user)
        return Response({
            "message": "OTP verified successfully",
            "refresh": token["refresh"],
            "access": token["access"],
            "is_new_user": created
        }, status=status.HTTP_200_OK)


class VerifyEmailOTPView(APIView):
    """
    Verifies OTP, creates user if not exists, and returns JWT tokens
    """
    def post(self, request):
        email = request.data.get("email")
        otp_code = request.data.get("otp_code")

        if not email or not otp_code:
            return Response({"error": "Email and OTP are required"}, status=status.HTTP_400_BAD_REQUEST)

        identifier = ""
        try:
            identifier = verify(otp_code, email)
        except OTPInvalidError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST) 

        # ✅ Create or get the user
        user, created = User.objects.get_or_create(
            email=identifier,
            defaults={"email": identifier}
        )

        # ✅ Issue JWT tokens
        token = issue_jwt_for_user(user)
        return Response({
            "message": "OTP verified successfully",
            "refresh": token["refresh"],
            "access": token["access"],
            "is_new_user": created
        }, status=status.HTTP_200_OK)
