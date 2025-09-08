from rest_framework import serializers

class VariantOptionSerializer(serializers.Serializer):
    name = serializers.CharField()
    price_diff = serializers.DecimalField(max_digits=10, decimal_places=2)

class VariantGroupSerializer(serializers.Serializer):
    name = serializers.CharField()
    is_required = serializers.BooleanField(default=True)
    options = VariantOptionSerializer(many=True)

class MenuItemAddonSerializer(serializers.Serializer):
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)

class MenuItemAddonGroupSerializer(serializers.Serializer):
    name = serializers.CharField()
    is_required = serializers.BooleanField(default=False)
    max_selection = serializers.IntegerField(default=0)
    addons = MenuItemAddonSerializer(many=True)

class MenuItemAvailabilitySerializer(serializers.Serializer):
    branch = serializers.CharField()
    is_available = serializers.BooleanField(default=True)
    override_price = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)

class MenuItemSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    image = serializers.CharField(required=False, allow_blank=True)
    variant_groups = VariantGroupSerializer(many=True, required=False)
    addon_groups = MenuItemAddonGroupSerializer(many=True, required=False)
    availabilities = MenuItemAvailabilitySerializer(many=True, required=False)

class MenuCategorySerializer(serializers.Serializer):
    name = serializers.CharField()
    sort_order = serializers.IntegerField(default=0)
    items = MenuItemSerializer(many=True)

class MenuSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(default=True)
    categories = MenuCategorySerializer(many=True)
