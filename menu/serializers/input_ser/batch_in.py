from rest_framework import serializers
from menu.models import BaseItemAvailability

class UploadFileItemSerializer(serializers.Serializer):
    """
    One file descriptor sent by the client.
    """
    ref_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    content_type = serializers.ChoiceField(choices=["image/jpeg", "image/png", "image/webp"])
    file_size = serializers.IntegerField(min_value=1)

    def validate_file_size(self, value: int) -> int:
        max_size = self.context.get("max_size_bytes", 5 * 1024 * 1024)
        if value > max_size:
            raise serializers.ValidationError("A file exceeds the 5MB limit.")
        return value


class BatchGenerateUploadURLRequestSerializer(serializers.Serializer):
    """
    Request payload: {"files": [{...}, {...}]}
    """
    files = UploadFileItemSerializer(many=True)

    def validate_files(self, files):
        max_batch = self.context.get("max_batch", 150)
        if not files:
            raise serializers.ValidationError("No files provided.")
        if len(files) > max_batch:
            raise serializers.ValidationError(f"Max {max_batch} files per batch.")
        return files

class ItemAvailabilityListSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="base_item.id")
    name = serializers.CharField(source="base_item.name")
    price = serializers.SerializerMethodField()
    is_available = serializers.BooleanField()

    class Meta:
        model = BaseItemAvailability
        fields = ["id", "name", "price", "is_available"]

    def get_price(self, obj):
        return obj.effective_price

class ItemAvailabilityUpdateItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    is_available = serializers.BooleanField()


class BulkItemAvailabilityUpdateSerializer(serializers.Serializer):
    items = ItemAvailabilityUpdateItemSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Items list cannot be empty")
        return value