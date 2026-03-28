# ─────────────────────────────────────────────────────────────────────────────
# serializers.py  —  Update-aware serializers
# Rule: no `id` field = CREATE, `id` only = SKIP, `id` + other fields = UPDATE
# ─────────────────────────────────────────────────────────────────────────────
from rest_framework import serializers
from urllib.parse import urlparse

class BaseUpdateSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)

class UpdateBaseItemSerializer(BaseUpdateSerializer):
    name        = serializers.CharField(required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    price       = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    image       = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_image(self, value):
        if not value:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https"):
            raise serializers.ValidationError("Image must be a valid http/https URL.")
        return value

    def validate(self, data):
        # CREATE path requires name + price
        if "id" not in data:
            if not data.get("name"):
                raise serializers.ValidationError("name is required when creating a base item.")
            if data.get("price") is None:
                raise serializers.ValidationError("price is required when creating a base item.")
        return data


class UpdateVariantOptionSerializer(BaseUpdateSerializer):
    name       = serializers.CharField(required=False)
    price_diff = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)


class UpdateVariantGroupSerializer(BaseUpdateSerializer):
    name        = serializers.CharField(required=False)
    is_required = serializers.BooleanField(required=False)
    options     = UpdateVariantOptionSerializer(many=True, required=False)


class UpdateMenuItemAddonSerializer(BaseUpdateSerializer):
    price     = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    base_item = UpdateBaseItemSerializer(required=False)


class UpdateMenuItemAddonGroupSerializer(BaseUpdateSerializer):
    name          = serializers.CharField(required=False)
    is_required   = serializers.BooleanField(required=False)
    max_selection = serializers.IntegerField(required=False)
    addons        = UpdateMenuItemAddonSerializer(many=True, required=False)


class UpdateMenuItemSerializer(BaseUpdateSerializer):
    custom_name  = serializers.CharField(required=False)
    description  = serializers.CharField(required=False, allow_blank=True)
    price        = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    image        = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    base_item    = UpdateBaseItemSerializer(required=False)
    variant_groups = UpdateVariantGroupSerializer(many=True, required=False)
    addon_groups   = UpdateMenuItemAddonGroupSerializer(many=True, required=False)


class UpdateMenuCategorySerializer(BaseUpdateSerializer):
    name       = serializers.CharField(required=False)
    sort_order = serializers.IntegerField(required=False)
    items      = UpdateMenuItemSerializer(many=True, required=False)


class UpdateMenuSerializer(BaseUpdateSerializer):
    name        = serializers.CharField(required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    is_active   = serializers.BooleanField(required=False)
    categories  = UpdateMenuCategorySerializer(many=True, required=False)