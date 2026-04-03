from rest_framework.response import Response
from rest_framework import status
from authflow.services import issue_jwt_for_user, request_email_otp, request_phone_otp, verify, OTPInvalidError
from django.contrib.auth import get_user_model
from accounts.serializers import InS
from accounts.serializers.input_ser.input_seriz import SendType
from rest_framework.generics import GenericAPIView
# do we have dedcted endpoints for sending otp for the admin registration since it still send the otp forward.

User = get_user_model()
class SendPhoneOTPView(GenericAPIView):
    serializer_class = InS.PhonenumberSendOptSerializer
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # vd = serializer.validated_data
        # return request_phone_otp(vd["phone_number"])
        return Response({"detail": "OTP sent.", "sent_at": "00:00:01"})

class SendEmailOTPView(GenericAPIView):
    serializer_class = InS.EmailOptSendSerializer
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        return request_email_otp(vd["email"])

class VerifyOTPView(GenericAPIView): # we need to revoke the jwt also use the refresh to get the new access, also the getting new refresh token
    """
    Verifies OTP, creates user if not exists, and returns JWT tokens
    """
    serializer_class = InS.PhonenumberOptSerializer
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        # try:
        #     identifier = verify(vd["otp_code"], vd["phone_number"])
        # except OTPInvalidError as e:
        #     return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)      
        identifier = vd["phone_number"]  

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

class VerifyEmailOTPView(GenericAPIView):
    """
    Verifies OTP, creates user if not exists, and returns JWT tokens
    """
    serializer_class = InS.PhonenumberOptSerializer
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        try:
            identifier = verify(vd["otp_code"], vd["email"])
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

# add a lond ulid string for this in some way stored in the system as otp and accessed via url or something
# maybe 2fa
class PassWordResetSendView(GenericAPIView): 
    serializer_class = InS.PasswordResetSendSerializer
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        send_type = vd["send_type"]
        
        if send_type == SendType.EMAIL.value:
            return request_email_otp(vd["email"])
        if send_type == SendType.PHONE.value:
            # return request_phone_otp(vd["phone_number"])
            return Response({"detail": "OTP sent.", "sent_at": "00:00:01"})
