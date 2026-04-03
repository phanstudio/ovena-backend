from rest_framework import serializers
from phonenumber_field.serializerfields import PhoneNumberField
from accounts.models import User

class UserInfoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()

class RegisterBAdminResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    refresh = serializers.CharField()
    access = serializers.CharField()
    user = UserInfoSerializer()

class OnboardResponseSerializer(serializers.Serializer):
    onboarding_step = serializers.IntegerField()
    is_onboarding_complete = serializers.BooleanField()


class UserSerializer(serializers.ModelSerializer):
    phone_number = PhoneNumberField()

    class Meta:
        model = User
        fields = ["id", "email", "phone_number", "name"]