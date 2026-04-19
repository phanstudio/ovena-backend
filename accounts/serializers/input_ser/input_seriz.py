from rest_framework import serializers
from phonenumber_field.serializerfields import PhoneNumberField # type: ignore
from enum import Enum

class SendType(Enum):
    PHONE = "phone"
    EMAIL = "email"

class AdminLoginSerializer(serializers.Serializer):
    phone_number = PhoneNumberField()
    password = serializers.CharField()

class DriverLoginSerializer(serializers.Serializer):
    phone_number = PhoneNumberField()
    password = serializers.CharField()

class PasswordResetSerializer(serializers.Serializer):
    phone_number = PhoneNumberField(required=False, allow_null=True)
    email = serializers.EmailField(required=False, allow_null=True)
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
    username = serializers.CharField(required=False, allow_blank=True)
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

class BaseVerifyOtpSerizer(serializers.Serializer):
    otp_code = serializers.CharField(required=False, allow_blank=True)

class PhonenumberOptSerializer(BaseVerifyOtpSerizer):
    phone_number = PhoneNumberField()

class EmailOptSerializer(BaseVerifyOtpSerizer):
    email = serializers.EmailField()

class PhonenumberSendOptSerializer(serializers.Serializer):
    phone_number = PhoneNumberField()

class EmailOptSendSerializer(serializers.Serializer):
    email = serializers.EmailField()

class PasswordResetSendSerializer(serializers.Serializer):
    send_type = serializers.ChoiceField(choices=[e.value for e in SendType], default="email")
    phone_number = PhoneNumberField(required=False, allow_null=True)
    email = serializers.EmailField(required=False, allow_null=True)

    def validate(self, data):
        send_type = data.get("send_type")
        phone = data.get("phone_number")
        email = data.get("email")

        if send_type == SendType.PHONE.value:
            if not phone:
                raise serializers.ValidationError({
                    "phone_number": f"This field is required when send_type is '{send_type}'."
                })

        elif send_type == SendType.EMAIL.value:
            if not email:
                raise serializers.ValidationError({
                    "email": f"This field is required when send_type is '{send_type}'."
                })

        return data

class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

class BranchClosedSerializer(serializers.Serializer):
    day = serializers.IntegerField(min_value=0, max_value=6)  # 0=Mon, 6=Sun
    is_closed = serializers.BooleanField(default=False)

# class BranchClosedSerializer(serializers.Serializer):
#     day = serializers.IntegerField(min_value=0, max_value=6)  # 0=Mon, 6=Sun
#     is_closed = serializers.BooleanField(default=False)
