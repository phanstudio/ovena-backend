from rest_framework import serializers
from menu.models import Order, OrderItem
from .models import FavoriteMenuItem, MenuItem
from addresses.serializers import LocationGetSerializer

class OrderHistorySerializer(serializers.ModelSerializer):
    driver = serializers.CharField(
        source="driver.full_name",
        read_only=True
    )

    branch = serializers.CharField(
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
            "branch",
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
        source="branch.address",
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
    
    def to_representation(self, instance):
        data = super().to_representation(instance)

        # menu_ids = set()

        # for item in instance.items.all():
        #     snap = item.snapshot or {}
        #     menu_item = snap.get("item") or {}
        #     menu_id = menu_item.get("id")
        #     if menu_id:
        #         menu_ids.add(menu_id)
        menu_ids = {
            item.menu_item_id
            for item in instance.items.all()
            if item.menu_item_id
        }

        menu_map = MenuItem.objects.filter(id__in=menu_ids).in_bulk()

        # attach image into response
        for item in data["items"]:
            menu_id = item["snapshot"]["item"]["id"]
            menu = menu_map.get(menu_id)

            if menu:
                item["snapshot"]["item"]["image"] = (
                    menu.image.url if menu.image else None
                )
                item["snapshot"]["item"]["id"] = menu_id
        # for item, obj in zip(data["items"], instance.items.all()):
        #     menu = menu_map.get(obj.menu_item_id)

        #     if menu:
        #         item["snapshot"]["item"]["image"] = (
        #             menu.image
        #         )
        #         item["snapshot"]["item"]["id"] = (
        #             obj.menu_item_id
        #         )

        return data


class FavoriteCreateSerializer(serializers.Serializer):
    menu_item_id = serializers.IntegerField()
    branch_id = serializers.IntegerField()


class MenuItemSerializer(serializers.ModelSerializer):
    # is_available = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = [
            "id",
            "custom_name", "description",
            "price", "image",
            # "is_available", 
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


class FavoriteListSerializer(serializers.ModelSerializer):
    menu_item = MenuItemSerializer(read_only=True)
    buisness_id = serializers.SerializerMethodField()

    class Meta:
        model = FavoriteMenuItem
        fields = ["menu_item", "created_at", "buisness_id"]
    
    def get_buisness_id(self, obj):
        try:
            return obj.branch.business.id if obj.branch else None
        except Exception:
            return None
        

class OrderCalculationGetSerializer(LocationGetSerializer):
    branch_id = serializers.IntegerField()
    coupon_code = serializers.CharField(required=False, allow_blank=True)
