from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from authflow.services import issue_jwt_for_user, send_email, verify_otp
from django.contrib.auth import get_user_model

# User = get_user_model()
# class SendEmailOTPView(APIView):
#     def post(self, request):
#         email = request.data.get("email")
#         if not email:
#             return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

#         result = send_email(email)
#         if "error" in result:
#             return Response(result, status=status.HTTP_400_BAD_REQUEST)
#         return Response(result, status=status.HTTP_200_OK)

# class VerifyEmailOTPView(APIView):
#     """
#     Verifies OTP, creates user if not exists, and returns JWT tokens
#     """
#     def post(self, request):
#         email = request.data.get("email")
#         otp_code = request.data.get("otp_code")

#         if not email or not otp_code:
#             return Response({"error": "Email and OTP are required"}, status=status.HTTP_400_BAD_REQUEST)

#         verified_id = verify_otp(otp_code)
#         if not verified_id and email != verified_id:
#             return Response({"error": "Invalid or expired OTP"}, status=status.HTTP_400_BAD_REQUEST)

#         # ✅ Create or get the user
#         user, created = User.objects.get_or_create(
#             email=email,
#             defaults={"email": email}
#         )

#         # ✅ Issue JWT tokens
#         token = issue_jwt_for_user(user)
#         return Response({
#             "message": "OTP verified successfully",
#             "refresh": token["refresh"],
#             "access": token["access"],
#             "is_new_user": created
#         }, status=status.HTTP_201_CREATED)
