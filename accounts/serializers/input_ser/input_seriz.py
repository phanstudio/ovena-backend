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
    password = serializers.CharField(write_only=True)


class CustomerLoginSerializer(LoginSerializer):
    phone_number = PhoneNumberField(required=False, allow_null=True)
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)

    def validate(self, data):
        if not data.get("phone_number") and not data.get("email"):
            raise serializers.ValidationError("Either phone_number or email is required.")
        return data


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
    phone_number = PhoneNumberField()
    password = serializers.CharField(write_only=True, min_length=8)
    username = serializers.CharField(required=False, allow_blank=True) # depreciated


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
    password = serializers.CharField(write_only=True)


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
