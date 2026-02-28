from rest_framework import serializers

class UserInfoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()

class RegisterBAdminResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    refresh = serializers.CharField()
    access = serializers.CharField()
    user = UserInfoSerializer()

class OnboardResponseSerializer(serializers.Serializer):
    admin_id = serializers.IntegerField()
    onboarding_step = serializers.IntegerField()
    is_onboarding_complete = serializers.BooleanField()
