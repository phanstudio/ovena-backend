from rest_framework.response import Response
from rest_framework import status
from authflow.services import request_email_otp, request_phone_otp, verify, OTPInvalidError, verify_phonenumber
from django.contrib.auth import get_user_model
from accounts.serializers import InS
from accounts.serializers.input_ser.input_seriz import SendType
from rest_framework.generics import GenericAPIView
from common.phone.utils import get_phone_number
from django.utils import timezone
from authflow.services.jwt import issue_jwt_for_user, issue_jwt_for_user_with_plan
from business_api.views import BaseBuisAdminAPIView
from accounts.services.profiles import (
    PROFILE_CUSTOMER,
)

# do we have dedcted endpoints for sending otp for the admin registration since it still send the otp forward.
# we need a dedicted page for sending otp but it has to be a user that is vwerfed so we ca track the account

User = get_user_model()

class GetSerilizerMixin():

    def get_verifed_data(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class SendOptMixin(GenericAPIView, GetSerilizerMixin):
    
    def request_data(self, vd):
        return 

    def post(self, request):
        vd = self.get_verifed_data(request)
        return self.request_data(vd)


class SendPhoneOTPMixin(SendOptMixin):
    serializer_class = InS.PhonenumberSendOptSerializer

    def request_data(self, _vd):
        # return request_phone_otp(get_phone_number(vd["phone_number"]))
        sent_at = timezone.now()
        return Response({"detail": "OTP sent.", "sent_at": sent_at.strftime("%b %d, %Y %H:%M:%S %Z"), 'pin_id': "98765433456789976"})


class SendEmailMixin(SendOptMixin):
    serializer_class = InS.EmailOptSendSerializer

    def request_data(self, vd):
        return request_email_otp(vd)


class SendPhoneOTPView(SendPhoneOTPMixin):
    ...


class SendEmailOTPView(SendEmailMixin):
    ...


class VerifyOtpMixin(GenericAPIView, GetSerilizerMixin):
    unidentified_id_lookup = ""

    def verify(self, vd):
        try:
            identifier = self.verfiy_function(vd)
        except OTPInvalidError as e:
            return None, Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return identifier, None

    def verfiy_function(self, vd):
        return verify(vd["otp_code"], vd[self.unidentified_id_lookup])
    
    def send_response(self, identifier):
        return
    
    def post(self, request):
        vd = self.get_verifed_data(request)
        identifier, error = self.verify(vd)
        if error:
            return error
        return self.send_response(identifier)


class VerifyPhoneOTPMixin(VerifyOtpMixin):
    """
    Verifies OTP, creates user if not exists, and returns JWT tokens
    """
    serializer_class = InS.PhonenumberOptSerializer
    unidentified_id_lookup = "phone_number"

    def verfiy_function(self, vd):
        # return verify_phonenumber(vd["otp_code"], get_phone_number(vd[self.unidentified_id_lookup]), vd["pin_id"])
        return vd[self.unidentified_id_lookup]

    def send_response(self, identifier):
        user, created = User.objects.get_or_create(
            phone_number=identifier,
            defaults={"phone_number": identifier}
        )

        if created:
            token = issue_jwt_for_user(user)
        else:
            token = issue_jwt_for_user_with_plan(user, active_profile=PROFILE_CUSTOMER)
        
        return Response({
            "message": "OTP verified successfully",
            "refresh": token["refresh"],
            "access": token["access"],
            "is_new_user": created
        }, status=status.HTTP_200_OK)


class VerifyEmailMixin(VerifyOtpMixin):
    serializer_class = InS.EmailOptSerializer
    unidentified_id_lookup = "email"
    
    def send_response(self, _identifier):
        return Response({"detail": "email verified"}, status=200)


class VerifyPhoneOTPView(VerifyPhoneOTPMixin): # we need to revoke the jwt also use the refresh to get the new access, also the getting new refresh token
    """
    Verifies OTP, creates user if not exists, and returns JWT tokens
    """
    ...


class VerifyEmailOTPView(VerifyEmailMixin):
    """
    Verifies OTP, creates user if not exists, and returns JWT tokens
    """

    def send_response(self, identifier):
        user, created = User.objects.get_or_create(
            email=identifier,
            defaults={"email": identifier}
        )

        if created:
            token = issue_jwt_for_user(user)
        else:
            token = issue_jwt_for_user_with_plan(user, active_profile=PROFILE_CUSTOMER)
        
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
        return request_email_otp(vd["email"])


## business admin
## add a check if the onboarding has finished so htay can't keep calling this endpoint
class SendEmailForRegistration(BaseBuisAdminAPIView, SendEmailMixin):
    ...

class VerifyEmailForRegistration(BaseBuisAdminAPIView, VerifyEmailMixin):
    ...
