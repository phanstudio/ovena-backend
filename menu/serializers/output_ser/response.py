from rest_framework import serializers

class UploadURLItemSerializer(serializers.Serializer):
    """
    One generated URL entry returned to the client.
    """
    ref_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    upload_url = serializers.URLField()
    public_url = serializers.URLField()

class BatchGenerateUploadURLResponseSerializer(serializers.Serializer):
    """
    Response payload: {"urls": [{...}, {...}]}
    """
    urls = UploadURLItemSerializer(many=True)

class IDListSerializer(serializers.Serializer):
    id = serializers.IntegerField()