from rest_framework import serializers

from driver_api.models import DriverNotification


class DriverNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverNotification
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

