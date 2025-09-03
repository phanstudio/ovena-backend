from rest_framework import serializers
from .models import Restaurant, Menu, MenuCategory, MenuItem, VariantGroup, VariantOption, MenuItemAddonGroup, MenuItemAddon

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
    class Meta:
        model = MenuItemAddon
        fields = ["id", "name", "price"]

class MenuItemAddonGroupSerializer(serializers.ModelSerializer):
    addons = MenuItemAddonSerializer(many=True, read_only=True)

    class Meta:
        model = MenuItemAddonGroup
        fields = ["id", "name", "is_required", "max_selection", "addons"]

class MenuItemSerializer(serializers.ModelSerializer):
    variant_groups = VariantGroupSerializer(many=True, read_only=True)
    addon_groups = MenuItemAddonGroupSerializer(many=True, read_only=True)

    class Meta:
        model = MenuItem
        fields = ["id", "name", "description", "price", "image", "variant_groups", "addon_groups"]

class MenuCategorySerializer(serializers.ModelSerializer):
    items = MenuItemSerializer(many=True, read_only=True)

    class Meta:
        model = MenuCategory
        fields = ["id", "name", "sort_order", "items"]

class MenuSerializer(serializers.ModelSerializer):
    categories = MenuCategorySerializer(many=True, read_only=True)

    class Meta:
        model = Menu
        fields = ["id", "name", "description", "is_active", "categories"]

class RestaurantSerializer(serializers.ModelSerializer):
    menus = MenuSerializer(many=True, read_only=True)

    class Meta:
        model = Restaurant
        fields = ["id", "company_name", "menus"]
