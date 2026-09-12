from rest_framework import serializers
from notifications.models import Notification

class NotificationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Notification

        fields = [
            "id",
            "notification_type",
            "title",
            "body",
            "payload_json",
            "is_read",
            "read_at",
            "created_at",
        ]


class BaseRegisterDeviceTokenSerialzer(serializers.Serializer):
    token = serializers.CharField()
    platform = serializers.CharField()
