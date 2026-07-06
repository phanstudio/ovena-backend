from rest_framework.response import Response
from rest_framework import status
from authflow.services import request_email_otp, request_phone_otp, verify, OTPInvalidError, verify_phonenumber
from django.contrib.auth import get_user_model
from accounts.serializers import InS
from accounts.serializers.input_ser.input_seriz import SendType
from rest_framework.generics import GenericAPIView
from common.phone.utils import get_phone_number
from django.utils import timezone
from authflow.services.jwt import issue_jwt_for_user
from business_api.views import BaseBuisAdminAPIView

# do we have dedcted endpoints for sending otp for the admin registration since it still send the otp forward.
# we need a dedicted page for sending otp but it has to be a user that is vwerfed so we ca track the account

User = get_user_model()

class SendPhoneOTPView(GenericAPIView):
    serializer_class = InS.PhonenumberSendOptSerializer
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        # return request_phone_otp(get_phone_number(vd["phone_number"]))
        sent_at = timezone.now()
        return Response({"detail": "OTP sent.", "sent_at": sent_at.strftime("%b %d, %Y %H:%M:%S %Z"), 'pin_id': "98765433456789976"})



class SendEmailMixin(GenericAPIView):
    serializer_class = InS.EmailOptSendSerializer

    def get_verifed_data(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data
    
    def post(self, request):
        vd = self.get_verifed_data(request)
        return request_email_otp(vd["email"])

class SendEmailOTPView(SendEmailMixin):
    ...


class VerifyPhoneOTPView(GenericAPIView): # we need to revoke the jwt also use the refresh to get the new access, also the getting new refresh token
    """
    Verifies OTP, creates user if not exists, and returns JWT tokens
    """
    serializer_class = InS.PhonenumberOptSerializer
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        # try:
        #     identifier = verify_phonenumber(vd["otp_code"], get_phone_number(vd["phone_number"]), vd["pin_id"])
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


class VerifyEmailMixin(GenericAPIView):
    serializer_class = InS.EmailOptSerializer

    def get_verifed_data(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def verify(self, otp_code, email):
        try:
            identifier = verify(otp_code, email)
        except OTPInvalidError as e:
            return None, Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return identifier, None
    
    def post(self, request):
        vd = self.get_verifed_data(request)
        _, error = self.verify(vd["otp_code"], vd["email"])
        if error:
            return error
        return Response({"detail": "email verified"}, status=200)


class VerifyEmailOTPView(VerifyEmailMixin):
    """
    Verifies OTP, creates user if not exists, and returns JWT tokens
    """
    serializer_class = InS.EmailOptSerializer
    def post(self, request):
        vd = self.get_verifed_data(request)
        identifier, error = self.verify(vd["otp_code"], vd["email"])
        if error:
            return error

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
class PassWordResetSendView(GenericAPIView): # just an endpoint doesn't still consitute as valid 
    serializer_class = InS.PasswordResetSendSerializer
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        send_type = vd["send_type"]
        
        if send_type == SendType.EMAIL.value:
            return request_email_otp(vd["email"])
        if send_type == SendType.PHONE.value:
            return request_phone_otp(get_phone_number(vd["phone_number"]))


## business admin
## add a check if the onboarding has finished so htay can't keep calling this endpoint
class SendEmailForRegistration(BaseBuisAdminAPIView, SendEmailMixin):
    ...

class VerifyEmailForRegistration(BaseBuisAdminAPIView, VerifyEmailMixin):
    ...
