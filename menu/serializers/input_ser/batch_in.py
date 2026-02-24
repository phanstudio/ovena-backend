from rest_framework import serializers


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
