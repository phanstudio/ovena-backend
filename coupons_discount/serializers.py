from django.utils import timezone
from rest_framework import serializers
from .models import Coupons, CouponWheel

class CouponSerializer(serializers.ModelSerializer):
    exhausted = serializers.SerializerMethodField()
    time_left_seconds = serializers.SerializerMethodField()

    class Meta:
        model = Coupons
        fields = [
            "id", "code", "description",
            "coupon_type", "scope",
            "discount_type", "discount_value",
            "max_uses", "uses_count",
            "valid_from", "valid_until",
            "exhausted",
            "time_left_seconds",
        ]

    def get_exhausted(self, obj):
        return obj.max_uses is not None and obj.uses_count >= obj.max_uses

    def get_time_left_seconds(self, obj):
        # If no end date => no countdown
        if not obj.valid_until:
            return None
        now = timezone.now()
        if obj.valid_from and now < obj.valid_from:
            return None
        # If already expired => 0
        delta = obj.valid_until - now
        return max(0, int(delta.total_seconds()))

class CouponWheelSerializer(serializers.ModelSerializer):
    coupons = CouponSerializer(many=True, read_only=True)

    class Meta:
        model = CouponWheel
        fields = ["id", "max_entries_amount", "is_active", "coupons"]

class CouponCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupons
        fields = [
            "id",
            "code", "description",
            "coupon_type", "category", "item",
            "buy_amount", "get_amount",
            "scope", "restaurant",
            "discount_type", "discount_value",
            "max_uses",
            "valid_from", "valid_until",
            "is_active",
        ]

    def validate(self, attrs):
        coupon_type = attrs.get("coupon_type", getattr(self.instance, "coupon_type", None))

        category = attrs.get("category", getattr(self.instance, "category", None))
        item = attrs.get("item", getattr(self.instance, "item", None))
        buy_amount = attrs.get("buy_amount", getattr(self.instance, "buy_amount", 0))
        get_amount = attrs.get("get_amount", getattr(self.instance, "get_amount", 0))

        scope = attrs.get("scope", getattr(self.instance, "scope", None))
        restaurant = attrs.get("restaurant", getattr(self.instance, "restaurant", None))
        valid_from = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        valid_until = attrs.get("valid_until", getattr(self.instance, "valid_until", None))

        # Scope rules
        if scope == "restaurant" and not restaurant:
            raise serializers.ValidationError({"restaurant": "Restaurant is required when scope=restaurant."})
        if scope == "global":
            attrs["restaurant"] = None

        # Type-specific rules
        if coupon_type == "categorydiscount" and not category:
            raise serializers.ValidationError({"category": "Category is required for categorydiscount."})

        if coupon_type == "itemdiscount" and not item:
            raise serializers.ValidationError({"item": "Item is required for itemdiscount."})

        if coupon_type == "BxGy":
            if buy_amount <= 0:
                raise serializers.ValidationError({"buy_amount": "buy_amount must be > 0 for BxGy."})
            if get_amount <= 0:
                raise serializers.ValidationError({"get_amount": "get_amount must be > 0 for BxGy."})
            # You likely need at least an item OR category for BxGy to define what it applies to
            if not item and not category:
                raise serializers.ValidationError(
                    {"detail": "BxGy should define an item or category (or add a 'buy_item/get_item' design)."}
                )

        if valid_from and valid_until and valid_until < valid_from:
            raise serializers.ValidationError({"valid_until": "valid_until must be >= valid_from."})

        return attrs

# coupons/serializers.py
from django.db.models import F
from .services import eligible_coupon_q

class CouponWheelSetSerializer(serializers.ModelSerializer):
    coupon_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = CouponWheel
        fields = ["id", "max_entries_amount", "is_active", "coupon_ids"]

    def validate(self, attrs):
        max_entries = attrs.get("max_entries_amount", getattr(self.instance, "max_entries_amount", 6))
        coupon_ids = attrs.get("coupon_ids", None)

        if max_entries <= 0:
            raise serializers.ValidationError({"max_entries_amount": "Must be > 0."})

        # If coupon_ids provided, ensure it doesn't exceed max_entries
        if coupon_ids is not None and len(coupon_ids) > max_entries:
            raise serializers.ValidationError({"coupon_ids": "Too many coupons for max_entries_amount."})

        return attrs

    def update(self, instance, validated_data):
        coupon_ids = validated_data.pop("coupon_ids", None)

        # Update wheel fields
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()

        # If coupons provided, set them (but only eligible ones)
        if coupon_ids is not None:
            eligible = Coupons.objects.filter(id__in=coupon_ids).filter(eligible_coupon_q()).distinct()
            instance.coupons.set(eligible)

        return instance
