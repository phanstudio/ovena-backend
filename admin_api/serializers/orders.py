from rest_framework import serializers

from menu.models import Order, OrderEvent
from accounts.models import DriverProfile


class AdminOrderEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderEvent
        fields = [
            'id', 'event_type', 'actor_type', 'actor_id',
            'old_status', 'new_status', 'metadata', 'timestamp',
        ]


class AdminOrderListSerializer(serializers.ModelSerializer):
    """Compact row for tables/lists — dashboards, cancellations, filters."""
    orderer_name = serializers.CharField(source='orderer.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    driver_name = serializers.CharField(source='driver.full_name', read_only=True, default=None)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'status', 'orderer_name', 'branch_name',
            'driver_name', 'subtotal', 'grand_total', 'payment_retry_count',
            'created_at', 'last_modified_at',
        ]


class AdminOrderDetailSerializer(serializers.ModelSerializer):
    """Full order view including its event timeline, for the order detail page."""
    events = AdminOrderEventSerializer(many=True, read_only=True)
    orderer_name = serializers.CharField(source='orderer.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    driver_name = serializers.CharField(source='driver.full_name', read_only=True, default=None)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'status', 'orderer_name', 'branch_name', 'driver_name',
            'subtotal', 'discount_total', 'items_total', 'delivery_price', 'grand_total',
            'payment_retry_count', 'last_payment_attempt', 'next_retry_at',
            'delivery_verified', 'picked_up_by_user',
            'created_at', 'confirmed_at', 'assigned_at', 'picked_up_at', 'delivered_at',
            'last_modified_at', 'estimated_delivery_time', 'events',
        ]


class AssignDriverSerializer(serializers.Serializer):
    driver_id = serializers.IntegerField()

    def validate_driver_id(self, value):
        if not DriverProfile.objects.filter(id=value).exists():
            raise serializers.ValidationError("Driver not found")
        return value


class ForceStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order._meta.get_field('status').choices)
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class CancelOrderSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False)
