from rest_framework import serializers


# ─────────────────────────────────────────────────────────────────────────────
# Shared
# ─────────────────────────────────────────────────────────────────────────────

class DeletedBaseItemsField(serializers.ListField):
    child = serializers.CharField()


# ─────────────────────────────────────────────────────────────────────────────
# Request serializers  —  validate incoming IDs
# ─────────────────────────────────────────────────────────────────────────────

class BulkDeleteRequestSerializer(serializers.Serializer):
    menus      = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    categories = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    items      = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    addons     = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    varity     = serializers.ListField(child=serializers.CharField(), required=False, default=list)

    def validate(self, data):
        if not any([data.get("menus"), data.get("categories"), data.get("items"), data.get("addons"), data.get("varity")]):
            raise serializers.ValidationError("At least one ID must be provided across menus, categories, items, or addons or varity.")
        return data


# ─────────────────────────────────────────────────────────────────────────────
# Response serializers  —  shape outgoing data
# ─────────────────────────────────────────────────────────────────────────────

class DeleteAddonResponseSerializer(serializers.Serializer):
    message           = serializers.CharField()
    addon_id          = serializers.CharField()
    base_item_deleted = serializers.BooleanField()


class DeleteMenuItemResponseSerializer(serializers.Serializer):
    message            = serializers.CharField()
    item_id            = serializers.CharField()
    base_items_deleted = DeletedBaseItemsField()


class DeleteCategoryResponseSerializer(serializers.Serializer):
    message            = serializers.CharField()
    category_id        = serializers.CharField()
    items_deleted      = serializers.IntegerField()
    base_items_deleted = DeletedBaseItemsField()


class DeleteMenuResponseSerializer(serializers.Serializer):
    message            = serializers.CharField()
    menu_id            = serializers.CharField()
    categories_deleted = serializers.IntegerField()
    items_deleted      = serializers.IntegerField()
    base_items_deleted = DeletedBaseItemsField()


class BulkDeletedCountsSerializer(serializers.Serializer):
    menus      = serializers.IntegerField()
    categories = serializers.IntegerField()
    items      = serializers.IntegerField()
    addons     = serializers.IntegerField()
    varity    = serializers.IntegerField()


class BulkDeleteResponseSerializer(serializers.Serializer):
    message            = serializers.CharField()
    deleted            = BulkDeletedCountsSerializer()
    base_items_deleted = DeletedBaseItemsField()