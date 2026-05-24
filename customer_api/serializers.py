from rest_framework import serializers
from menu.models import Order, OrderItem

class OrderHistorySerializer(serializers.ModelSerializer):
    driver = serializers.CharField(
        source="driver.full_name",
        read_only=True
    )
    branch = serializers.CharField(
        source="branch.display_name",
        read_only=True
    )
    class Meta:
        model = Order
        fields = [
            "id",
            "branch",
            "driver",
            "grand_total",
            "order_number",
            "status",
            "created_at",
        ]

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


