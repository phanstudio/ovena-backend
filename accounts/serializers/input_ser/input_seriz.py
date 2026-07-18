from rest_framework import serializers
from phonenumber_field.serializerfields import PhoneNumberField  # type: ignore
from enum import Enum


class SendType(Enum):
    PHONE = "phone"
    EMAIL = "email"


class LoginResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    refresh = serializers.CharField()
    access = serializers.CharField()


class LoginSerializer(serializers.Serializer):
    phone_number = PhoneNumberField()
    password = serializers.CharField()


class AdminLoginSerializer(LoginSerializer):
    ...


class DriverLoginSerializer(LoginSerializer):
    ...


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()
    new_password = serializers.CharField()
    otp_code = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    password = serializers.CharField()
    new_password = serializers.CharField()


class LinkRequestSerializer(serializers.Serializer):
    branch_id = serializers.IntegerField()


class LinkApproveSerializer(serializers.Serializer):
    otp = serializers.CharField()
    device_id = serializers.CharField()
    # branch_id = serializers.IntegerField()
    phone_number = PhoneNumberField()
    username = serializers.CharField(required=False, allow_blank=True) # depeciated
    # password = serializers.CharField()


class AppAdminRequestSerializer(serializers.Serializer):
    role = serializers.CharField()


class AppAdminApproveSerializer(serializers.Serializer):
    otp = serializers.CharField()
    phone_number = PhoneNumberField()
    password = serializers.CharField()
    full_name = serializers.CharField()
    email = serializers.EmailField()


class LinkStaffLoginSerializer(serializers.Serializer):
    device_id = serializers.CharField()
    # password = serializers.CharField()
    # branch_id = serializers.CharField() or int
    # phone_number = PhoneNumberField()


class BaseVerifyOtpSerizer(serializers.Serializer):
    otp_code = serializers.CharField(required=False, allow_blank=True)


class PhonenumberOptSerializer(BaseVerifyOtpSerizer):
    phone_number = PhoneNumberField()
    pin_id = serializers.CharField()


class EmailOptSerializer(BaseVerifyOtpSerizer):
    email = serializers.EmailField()


class PhonenumberSendOptSerializer(serializers.Serializer):
    phone_number = PhoneNumberField()


class EmailOptSendSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetSendSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_null=True)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class BranchClosedSerializer(serializers.Serializer):
    # day = serializers.IntegerField(min_value=0, max_value=6)  # 0=Mon, 6=Sun
    is_closed = serializers.BooleanField(default=False)


# class BranchClosedSerializer(serializers.Serializer):
#     day = serializers.IntegerField(min_value=0, max_value=6)  # 0=Mon, 6=Sun
#     is_closed = serializers.BooleanField(default=False)
