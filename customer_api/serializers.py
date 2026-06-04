from rest_framework import serializers
from menu.models import Order, OrderItem
from .models import FavoriteMenuItem

class OrderHistorySerializer(serializers.ModelSerializer):
    driver = serializers.CharField(
        source="driver.full_name",
        read_only=True
    )

    location = serializers.CharField(
        source="branch.display_name",
        read_only=True
    )

    product_name = serializers.SerializerMethodField()
    product_image = serializers.SerializerMethodField()
    extra_items = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "product_name",
            "product_image",
            "extra_items",
            "location",
            "driver",
            "grand_total",
            "order_number",
            "status",
            "created_at",
        ]
    
    def _first_item(self, obj):
        if not hasattr(obj, "_first_item"):
            obj._first_item = next(iter(obj.items.all()), None)
        return obj._first_item

    def _item_count(self, obj):
        if not hasattr(obj, "_item_count"):
            obj._item_count = len(obj.items.all())
        return obj._item_count

    def get_extra_items(self, obj):
        return max(self._item_count(obj) - 1, 0)

    # def get_extra_items(self, obj):
    #     items = self._items(obj)
    #     return max(len(items) - 1, 0)

    # def _first_item(self, obj):
    #     items = self._items(obj)

    #     if not items:
    #         return None

    #     return items[0]

    def get_product_name(self, obj):
        item = self._first_item(obj)

        if not item:
            return None

        snap = item.snapshot or {}
        return snap.get("menu_item")

    def get_product_image(self, obj):
        item = self._first_item(obj)

        if not item:
            return None

        snap = item.snapshot or {}
        return snap.get("menu_item_image")


class OrderItemSerializer(serializers.ModelSerializer):
    snapshot = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ["quantity", "line_total", "snapshot"]

    def get_snapshot(self, obj):
        snap = obj.snapshot or {}

        return {
            "item": snap.get("menu_item"),
            "options": [
                f"{v.get('group_name')} - {v.get('option_name')}"
                for v in snap.get("variants", [])
            ],
            "addons": [a.get("name") for a in snap.get("addons", [])],
        }

class OrderRetrieveSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(
        source="driver.full_name",
        read_only=True
    )
    driver_vehicle = serializers.CharField(
        source="driver.vehicle_type",
        read_only=True
    )
    branch_name = serializers.CharField(
        source="branch.display_name",
        read_only=True
    )
    branch_address = serializers.CharField(
        source="address",
        read_only=True
    )
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "branch_name",
            "branch_address",
            "driver_name",
            "driver_vehicle",
            "grand_total",
            "order_number",
            "status",
            "created_at",
            "items",
        ]

class FavoriteCreateSerializer(serializers.Serializer):
    menu_item_id = serializers.IntegerField()

class FavoriteListSerializer(serializers.ModelSerializer):
    class Meta:
        model = FavoriteMenuItem
        fields = ["menu_item", "created_at"]
