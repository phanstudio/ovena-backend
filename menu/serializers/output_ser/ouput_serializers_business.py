from rest_framework import serializers
from menu.models import (
    Menu, MenuCategory, MenuItem, VariantGroup,
    VariantOption, MenuItemAddonGroup, MenuItemAddon
)

class VariantOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = VariantOption
        fields = ["id", "name", "price_diff"]

class VariantGroupSerializer(serializers.ModelSerializer):
    options = VariantOptionSerializer(many=True, read_only=True)

    class Meta:
        model = VariantGroup
        fields = ["id", "name", "is_required", "options"]

class MenuItemAddonSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    class Meta:
        model = MenuItemAddon
        fields = ["id", "name", "price"]
    
    def get_name(self, obj):
        return obj.base_item.name

class MenuItemAddonGroupSerializer(serializers.ModelSerializer):
    addons = MenuItemAddonSerializer(many=True, read_only=True)

    class Meta:
        model = MenuItemAddonGroup
        fields = ["id", "name", "is_required", "max_selection", "addons"]

class MenuItemSerializer(serializers.ModelSerializer):
    variant_groups = VariantGroupSerializer(many=True, read_only=True)
    addon_groups = MenuItemAddonGroupSerializer(many=True, read_only=True)

    base_item_id = serializers.IntegerField(source="base_item.id", read_only=True)
    is_available = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = [
            "id",
            "base_item_id",
            "custom_name",
            "description",
            "price",
            "image",
            "is_available",
            "variant_groups",
            "addon_groups",
        ]

    def get_is_available(self, obj):
        branch = self.context.get("branch")

        if not branch:
            return True

        availability = obj.base_item.item_availabilities.filter(
            branch=branch
        ).first()

        if availability:
            return availability.is_available

        return True

class MenuCategorySerializer(serializers.ModelSerializer):
    items = MenuItemSerializer(many=True, read_only=True)

    class Meta:
        model = MenuCategory
        fields = ["id", "name", "sort_order", "items"]

class BusinessMenuSerializer(serializers.ModelSerializer):
    categories = MenuCategorySerializer(many=True, read_only=True)

    class Meta:
        model = Menu
        fields = ["id", "name", "description", "is_active", "categories"]
