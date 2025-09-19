from rest_framework import serializers

# Check description and name becuase they are set at initail creation of all this, 
class BaseItemSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)  # default_price
    image = serializers.CharField(required=False, allow_blank=True)  # canonical

class VariantOptionSerializer(serializers.Serializer):
    name = serializers.CharField()
    price_diff = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)


class VariantGroupSerializer(serializers.Serializer):
    name = serializers.CharField()
    is_required = serializers.BooleanField(default=True)
    options = VariantOptionSerializer(many=True)


class MenuItemAddonSerializer(serializers.Serializer):
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    base_item = BaseItemSerializer()   # wraps a base item (e.g., "Cheese Slice")


class MenuItemAddonGroupSerializer(serializers.Serializer):
    name = serializers.CharField()
    is_required = serializers.BooleanField(default=False)
    max_selection = serializers.IntegerField(default=0)
    addons = MenuItemAddonSerializer(many=True)


class MenuItemSerializer(serializers.Serializer):
    custom_name = serializers.CharField(required=False)  # wrapper label, e.g. "Cheeseburger"
    description = serializers.CharField(required=False, allow_blank=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    image = serializers.CharField(required=False, allow_blank=True)  # optional override

    base_item = BaseItemSerializer()  # every menu item must wrap a base item

    variant_groups = VariantGroupSerializer(many=True, required=False)
    addon_groups = MenuItemAddonGroupSerializer(many=True, required=False)
    

class MenuCategorySerializer(serializers.Serializer):
    name = serializers.CharField()
    sort_order = serializers.IntegerField(default=0)
    items = MenuItemSerializer(many=True)


class MenuSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(default=True)
    categories = MenuCategorySerializer(many=True)
