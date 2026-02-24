from rest_framework import serializers

class AdminLoginSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    password = serializers.CharField()

class DriverLoginSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    password = serializers.CharField()

class PasswordResetSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    new_password = serializers.CharField()
    otp_code = serializers.CharField()


# phone number reated check later
# import phonenumbers
# from rest_framework import serializers

# class PhoneField(serializers.CharField):
#     def __init__(self, default_region="NG", **kwargs):
#         super().__init__(**kwargs)
#         self.default_region = default_region

#     def to_internal_value(self, data):
#         raw = super().to_internal_value(data).strip()

#         # handle "234xxxxxxxxxx" -> "+234xxxxxxxxxx"
#         if raw.isdigit() and len(raw) >= 11 and raw.startswith("234"):
#             raw = "+" + raw

#         try:
#             # If raw doesn't start with +, parse with default region
#             if raw.startswith("+"):
#                 num = phonenumbers.parse(raw, None)
#             else:
#                 num = phonenumbers.parse(raw, self.default_region)

#             if not phonenumbers.is_valid_number(num):
#                 raise serializers.ValidationError("Invalid phone number")

#             # Normalize to E.164
#             return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)

#         except phonenumbers.NumberParseException:
#             raise serializers.ValidationError("Invalid phone number")