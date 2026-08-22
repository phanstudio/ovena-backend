from rest_framework import serializers
from menu.models.categories import TagGroup, GlobalTag
import json

class CategoryTagsUpdateSerializer(serializers.Serializer):
    tag_ids = serializers.ListField(child=serializers.IntegerField())

class GlobalTagCreateSerializer(serializers.Serializer):
    name = serializers.CharField()

class TagGroupSerializer(serializers.ModelSerializer):
    tags_count = serializers.IntegerField(source="tags.count", read_only=True)
    tags = serializers.PrimaryKeyRelatedField(
        queryset=GlobalTag.objects.all(), many=True, required=False
    )

    class Meta:
        model = TagGroup
        fields = ["id", "name", "slug", "images", "tags", "tags_count"]
        read_only_fields = ["id", "slug", "tags_count"]

    def to_internal_value(self, data):
        data = data.copy()

        if "tags" in data and isinstance(data["tags"], str):
            try:
                data["tags"] = json.loads(data["tags"])
            except json.JSONDecodeError:
                pass

        return super().to_internal_value(data)

    def update(self, instance, validated_data):
        tags = validated_data.pop("tags", None)
        instance = super().update(instance, validated_data)
        if tags is not None:
            instance.tags.set(tags)  # full replace, same pattern as CategoryTagsUpdateSerializer
        return instance

    def create(self, validated_data):
        tags = validated_data.pop("tags", [])
        instance = super().create(validated_data)
        if tags:
            instance.tags.set(tags)
        return instance

class GlobalTagSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(
        source="group.name",
        read_only=True
    )

    class Meta:
        model = GlobalTag
        fields = [
            "id",
            "name",
            "slug",
            "group",
            "group_name",
        ]
        read_only_fields = ["id", "slug", "group_name"]

class CategorySearchInputSerializer(serializers.Serializer):
    category_id = serializers.IntegerField()  # TagGroup id
