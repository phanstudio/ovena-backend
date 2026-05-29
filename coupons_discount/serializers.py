from django.utils import timezone
from rest_framework import serializers

from .models import Coupons, CouponWheel, UserCouponWallet
from .services import eligible_coupon_q, eligible_coupon_for_wheel_q


# ---------------------------------------------------------------------------
# Coupon read serializer (used in wheel display, wallet, etc.)
# ---------------------------------------------------------------------------

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
            "buy_amount", "get_amount",
            "buy_item", "get_item",
            "is_reward", "exhausted",
            "time_left_seconds",
        ]

    def get_exhausted(self, obj: Coupons) -> bool:
        return obj.max_uses is not None and obj.uses_count >= obj.max_uses

    def get_time_left_seconds(self, obj: Coupons) -> int | None:
        if not obj.valid_until:
            return None
        now = timezone.now()
        if obj.valid_from and now < obj.valid_from:
            return None
        delta = obj.valid_until - now
        return max(0, int(delta.total_seconds()))


# ---------------------------------------------------------------------------
# Wheel serializers
# ---------------------------------------------------------------------------

class CouponWheelBaseSerializer(serializers.ModelSerializer):
    """Read-only view of the wheel including its eligible reward coupons."""
    class Meta:
        model = CouponWheel
        fields = ["id", "max_entries_amount", "is_active"]


class CouponWheelSerializer(CouponWheelBaseSerializer):
    """Read-only view of the wheel including its eligible reward coupons."""
    coupons = CouponSerializer(many=True, read_only=True)

    class Meta(CouponWheelBaseSerializer.Meta):
        fields = CouponWheelBaseSerializer.Meta.fields + ["coupons"]


class CouponWheelSetSerializer(CouponWheelBaseSerializer):
    """Admin serializer for configuring the wheel's coupons."""

    coupon_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
    )

    class Meta(CouponWheelBaseSerializer.Meta):
        fields = CouponWheelBaseSerializer.Meta.fields + ["coupon_ids"]

    def validate(self, attrs):
        max_entries = attrs.get(
            "max_entries_amount", getattr(self.instance, "max_entries_amount", 6)
        )
        coupon_ids = attrs.get("coupon_ids")

        if max_entries <= 0:
            raise serializers.ValidationError({"max_entries_amount": "Must be > 0."})

        if coupon_ids is not None and len(coupon_ids) > max_entries:
            raise serializers.ValidationError(
                {"coupon_ids": "Too many coupons for max_entries_amount."}
            )

        return attrs

    def update(self, instance: CouponWheel, validated_data: dict) -> CouponWheel:
        coupon_ids = validated_data.pop("coupon_ids", None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()

        if coupon_ids is not None:
            # Only is_reward=True coupons that are still eligible may be on the wheel.
            eligible = (
                Coupons.objects
                .filter(id__in=coupon_ids)
                .filter(eligible_coupon_for_wheel_q())
                .distinct()
            )

            eligible_ids = set(eligible.values_list("id", flat=True))
            skipped_ids = [cid for cid in coupon_ids if cid not in eligible_ids]

            instance.coupons.set(eligible)

            # Surface which IDs were silently dropped so the caller can inform the admin.
            self._skipped_coupon_ids = skipped_ids

        return instance


# ---------------------------------------------------------------------------
# Coupon create / update (admin)
# ---------------------------------------------------------------------------

class CouponCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupons
        fields = [
            "id", "code", 
            "description", "max_uses",
            "coupon_type", "category", "item",
            "buy_amount", "get_amount",
            "buy_item", "get_item",
            "scope", "business",
            "discount_type", "discount_value",
            "valid_from", "valid_until",
            "is_active", "is_reward",
        ]

    def validate(self, attrs):
        coupon_type = attrs.get("coupon_type", getattr(self.instance, "coupon_type", None))
        is_reward = attrs.get("is_reward", getattr(self.instance, "is_reward", False))

        category = attrs.get("category", getattr(self.instance, "category", None))
        item = attrs.get("item", getattr(self.instance, "item", None))
        buy_amount = attrs.get("buy_amount", getattr(self.instance, "buy_amount", 0))
        get_amount = attrs.get("get_amount", getattr(self.instance, "get_amount", 0))
        buy_item = attrs.get("buy_item", getattr(self.instance, "buy_item", None))
        get_item = attrs.get("get_item", getattr(self.instance, "get_item", None))
        scope = attrs.get("scope", getattr(self.instance, "scope", None))
        business = attrs.get("business", getattr(self.instance, "business", None))
        valid_from = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        valid_until = attrs.get("valid_until", getattr(self.instance, "valid_until", None))

        # Reward coupons must have a finite max_uses so the wheel can exhaust them.
        if is_reward:
            max_uses = attrs.get("max_uses", getattr(self.instance, "max_uses", None))
            if not max_uses:
                raise serializers.ValidationError(
                    {"max_uses": "Reward coupons must have a max_uses limit."}
                )

        # Scope rules.
        if scope == "business" and not business:
            raise serializers.ValidationError(
                {"business": "Business is required when scope=business."}
            )
        if scope == "global":
            attrs["business"] = None

        # Type-specific rules.
        if coupon_type == "categorydiscount" and not category:
            raise serializers.ValidationError(
                {"category": "Category is required for categorydiscount."}
            )
        if coupon_type == "itemdiscount" and not item:
            raise serializers.ValidationError(
                {"item": "Item is required for itemdiscount."}
            )
        if coupon_type == "BxGy":
            if buy_amount <= 0:
                raise serializers.ValidationError(
                    {"buy_amount": "buy_amount must be > 0 for BxGy."}
                )
            if get_amount <= 0:
                raise serializers.ValidationError(
                    {"get_amount": "get_amount must be > 0 for BxGy."}
                )
            if not buy_item:
                raise serializers.ValidationError(
                    {"buy_item": "buy_item is required for BxGy."}
                )
            if not get_item:
                raise serializers.ValidationError(
                    {"get_item": "get_item is required for BxGy."}
                )
        else:
            if buy_item or get_item:
                raise serializers.ValidationError(
                    {"detail": "buy_item/get_item can only be used with coupon_type=BxGy."}
                )

        if valid_from and valid_until and valid_until < valid_from:
            raise serializers.ValidationError(
                {"valid_until": "valid_until must be >= valid_from."}
            )

        if coupon_type == "BxGy" and scope == "business" and business:
            buy_business = getattr(
                getattr(getattr(buy_item, "category", None), "menu", None), "business", None
            )
            get_business = getattr(
                getattr(getattr(get_item, "category", None), "menu", None), "business", None
            )
            if buy_business and buy_business != business:
                raise serializers.ValidationError(
                    {"buy_item": "buy_item must belong to the selected business."}
                )
            if get_business and get_business != business:
                raise serializers.ValidationError(
                    {"get_item": "get_item must belong to the selected business."}
                )

        return attrs


# ---------------------------------------------------------------------------
# User wallet serializers
# ---------------------------------------------------------------------------

class UserCouponWalletSerializer(serializers.ModelSerializer):
    """
    Read-only view of a user's reward coupon wallet entries.
    Exposes the coupon details inline so the client can show
    discount information without a second request.
    """

    coupon = CouponSerializer(read_only=True)
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = UserCouponWallet
        fields = [
            "id",
            "coupon",
            "awarded_at",
            "awarded_from_wheel_spin",
            "is_used",
            "used_at",
            "is_expired",
        ]
        read_only_fields = fields

    def get_is_expired(self, obj: UserCouponWallet) -> bool:
        """True if the underlying coupon's validity window has closed."""
        c = obj.coupon
        if not c.is_active:
            return True
        now = timezone.now()
        if c.valid_from and now < c.valid_from:
            return True
        if c.valid_until and now > c.valid_until:
            return True
        return False



