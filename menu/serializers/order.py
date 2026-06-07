from decimal import Decimal
# from django.db import transaction
from rest_framework import serializers

from accounts.models import Branch
from addresses.utils import get_cached_distance_km_from_2points
from authflow.services import generate_passphrase, hash_phrase
from coupons_discount.models import Coupons, UserCouponWallet
from coupons_discount.services import CouponService, eligible_coupon_q, available_wallet_entry_q
from menu.models import (
    BaseItemAvailability, MenuItem, MenuItemAddon, Order, OrderItem, VariantOption,
)

PRICE_PER_KM = 1000
MINIMUM_PRICE_KM = 100 #1000
MIN_ORDER_SUBTOTAL = Decimal("5000.00")

def calculate_delivery_fee(customer, distance_km)-> float:
    delivery_fee = max(distance_km * PRICE_PER_KM, MINIMUM_PRICE_KM)
    if customer.pickup_food:
        delivery_fee = 0
    return delivery_fee


class OrderItemCreateSerializer(serializers.Serializer):
    menu_item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    variant_option_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )
    addon_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )


class OrderCreateSerializer(serializers.Serializer):
    branch_id = serializers.IntegerField()

    # Marketing coupon: user types a code.
    coupon_code = serializers.CharField(required=False, allow_blank=True, default="")

    # Reward coupon: user selects from their wallet.
    # Exactly one of coupon_code / wallet_entry_id may be supplied per order.
    wallet_entry_id = serializers.IntegerField(required=False, allow_null=True, default=None)

    items = OrderItemCreateSerializer(many=True)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, attrs):
        # request = self.context["request"]
        user = self.context["user"]
        user_loaction = self.context["user_location"]
        branch_id = attrs["branch_id"]
        items = attrs.get("items") or []

        # 1) Require items.
        if not items:
            raise serializers.ValidationError({"items": "An order must have at least one item."})

        # 2) Validate branch.
        branch = Branch.objects.filter(id=branch_id, is_active=True).first()
        if not branch:
            raise serializers.ValidationError({"branch_id": "Invalid branch."})
        if not branch.is_accepting_orders:
            raise serializers.ValidationError(
                {"branch_id": "This restaurant is not accepting orders right now."}
            )
        attrs["branch"] = branch
        
        
        # 3) Resolve the requesting user and delivery distance.
        attrs["distance_km"] = get_cached_distance_km_from_2points(
            user_loaction, branch.location
        )
        attrs["_user"] = user

        # 4) Coupon resolution — mutually exclusive paths.
        coupon_code = (attrs.get("coupon_code") or "").strip()
        wallet_entry_id = attrs.get("wallet_entry_id")

        if coupon_code and wallet_entry_id:
            raise serializers.ValidationError(
                {"non_field_errors": "Supply either coupon_code or wallet_entry_id, not both."}
            )

        coupon = None
        wallet_entry = None

        if coupon_code:
            # Marketing coupon path.
            coupon = (
                Coupons.objects
                .filter(code=coupon_code, is_reward=False)
                .filter(eligible_coupon_q())
                .first()
            )
            if not coupon:
                raise serializers.ValidationError(
                    {"coupon_code": "Coupon not found or no longer valid."}
                )

        elif wallet_entry_id is not None:
            # Reward coupon path: resolve the wallet entry belonging to this user.
            wallet_entry = (
                UserCouponWallet.objects
                .select_related("coupon")
                .filter(
                    pk=wallet_entry_id,
                    user=user,
                )
                .filter(available_wallet_entry_q())
                .first()
            )
            if not wallet_entry:
                raise serializers.ValidationError(
                    {"wallet_entry_id": "Wallet entry not found, already used, or does not belong to you."}
                )
            coupon = wallet_entry.coupon

            # Confirm the coupon itself is still within its validity window.
            from django.utils import timezone
            now = timezone.now()
            still_valid = (
                Coupons.objects
                .filter(pk=coupon.pk, is_active=True, valid_from__lte=now)
                .filter(
                    __import__("django.db.models", fromlist=["Q"]).Q(valid_until__isnull=True)
                    | __import__("django.db.models", fromlist=["Q"]).Q(valid_until__gte=now)
                )
                .exists()
            )
            if not still_valid:
                raise serializers.ValidationError(
                    {"wallet_entry_id": "This reward coupon has expired and can no longer be redeemed."}
                )

        attrs["coupon"] = coupon
        attrs["wallet_entry"] = wallet_entry

        # 5) Preload menu items.
        menu_item_ids = [i["menu_item_id"] for i in items]
        menu_items = MenuItem.objects.select_related("base_item").filter(id__in=menu_item_ids)
        menu_map = {m.id: m for m in menu_items}
        missing = [mid for mid in menu_item_ids if mid not in menu_map]
        if missing:
            raise serializers.ValidationError({"items": f"MenuItem not found: {missing}"})

        # 6) Branch availability + pricing.
        base_item_ids = [menu_map[mid].base_item_id for mid in menu_item_ids]
        avails = BaseItemAvailability.objects.filter(branch=branch, base_item_id__in=base_item_ids)
        avail_map = {a.base_item_id: a for a in avails}

        # 7) Preload variants / addons.
        all_variant_ids: set = set()
        all_addon_ids: set = set()
        for i in items:
            all_variant_ids.update(i.get("variant_option_ids") or [])
            all_addon_ids.update(i.get("addon_ids") or [])

        variant_map = {
            v.id: v
            for v in VariantOption.objects.select_related("group", "group__item").filter(
                id__in=all_variant_ids
            )
        }
        addon_map = {
            a.id: a
            for a in MenuItemAddon.objects.prefetch_related("groups").filter(id__in=all_addon_ids)
        }

        bad_variants = [vid for vid in all_variant_ids if vid not in variant_map]
        bad_addons = [aid for aid in all_addon_ids if aid not in addon_map]
        if bad_variants:
            raise serializers.ValidationError({"items": f"VariantOption not found: {bad_variants}"})
        if bad_addons:
            raise serializers.ValidationError({"items": f"Addon not found: {bad_addons}"})

        # 8) Per-item validation and price calculation.
        subtotal = Decimal("0.00")

        for entry in items:
            menu_item = menu_map[entry["menu_item_id"]]
            qty = int(entry["quantity"])

            avail = avail_map.get(menu_item.base_item_id)
            base_price = avail.effective_price if avail else Decimal(menu_item.effective_price)

            chosen_variant_ids = entry.get("variant_option_ids") or []
            chosen_addon_ids = entry.get("addon_ids") or []

            # Variants belong to this menu item.
            chosen_variants = [variant_map[vid] for vid in chosen_variant_ids]
            for v in chosen_variants:
                if v.group.item_id != menu_item.id:
                    raise serializers.ValidationError(
                        {"items": f"VariantOption {v.id} does not belong to MenuItem {menu_item.id}."}
                    )

            # Required variant groups.
            required_groups = set(
                menu_item.variant_groups.filter(is_required=True).values_list("id", flat=True)
            )
            chosen_groups = {v.group_id for v in chosen_variants}
            missing_groups = required_groups - chosen_groups
            if missing_groups:
                raise serializers.ValidationError(
                    {
                        "items": (
                            f"Missing required variant group(s) {sorted(missing_groups)} "
                            f"for MenuItem {menu_item.id}."
                        )
                    }
                )

            variant_total = sum(Decimal(v.price_diff) for v in chosen_variants)

            # Addons belong to this menu item.
            chosen_addons = [addon_map[aid] for aid in chosen_addon_ids]
            item_group_ids = set(menu_item.addon_groups.values_list("id", flat=True))
            for a in chosen_addons:
                if not (set(a.groups.values_list("id", flat=True)) & item_group_ids):
                    raise serializers.ValidationError(
                        {"items": f"Addon {a.id} is not allowed for MenuItem {menu_item.id}."}
                    )

            # Max selection per addon group.
            counts: dict[int, int] = {gid: 0 for gid in item_group_ids}
            for a in chosen_addons:
                for gid in set(a.groups.values_list("id", flat=True)) & item_group_ids:
                    counts[gid] += 1
            group_rules = {g.id: g.max_selection for g in menu_item.addon_groups.all()}
            for gid, count in counts.items():
                max_sel = int(group_rules.get(gid, 0) or 0)
                if max_sel > 0 and count > max_sel:
                    raise serializers.ValidationError(
                        {"items": f"Too many addons for group {gid}. Max is {max_sel}."}
                    )

            addon_total = sum(Decimal(a.price) for a in chosen_addons)
            line_total = (base_price + variant_total + addon_total) * Decimal(qty)
            subtotal += line_total

            # Stash for create().
            entry["_menu_item"] = menu_item
            entry["_base_price"] = base_price
            entry["_variant_total"] = variant_total
            entry["_addon_total"] = addon_total
            entry["_line_total"] = line_total
            entry["_variants"] = chosen_variants
            entry["_addons"] = chosen_addons

        # 9) Minimum order value.
        if subtotal < MIN_ORDER_SUBTOTAL:
            raise serializers.ValidationError(
                {
                    "items": (
                        f"Minimum order subtotal is {MIN_ORDER_SUBTOTAL}. "
                        f"Current subtotal is {subtotal}."
                    )
                }
            )

        attrs["_subtotal"] = subtotal
        return attrs

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create(self, validated_data):
        # user = self.context["user"]
        customer = self.context["customer"]
        branch = validated_data["branch"]
        coupon: Coupons | None = validated_data.get("coupon")
        wallet_entry: UserCouponWallet | None = validated_data.get("wallet_entry")
        items = validated_data["items"]
        distance_km = validated_data.get("distance_km", 0)

        phrase = generate_passphrase()
        
        delivery_fee = calculate_delivery_fee(customer, distance_km)

        order = Order.objects.create(
            orderer=customer,
            branch=branch,
            delivery_secret_hash=hash_phrase(phrase),
            delivery_price=delivery_fee,
            picked_up_by_user = customer.pickup_food,
        )

        # Bulk-create order items.
        order_items_to_create = []
        for entry in items:
            qty = int(entry["quantity"])
            base_price = entry["_base_price"]
            menu_item = entry["_menu_item"]
            variant_total = entry["_variant_total"]
            addon_total = entry["_addon_total"]
            added_total = variant_total + addon_total
            line_total = entry["_line_total"]
            chosen_variants = entry["_variants"]
            chosen_addons = entry["_addons"]

            snapshot = {
                "menu_item": {
                    "id": menu_item.id,
                    "name": menu_item.custom_name or menu_item.base_item.name,
                },
                "pricing": {
                    "base_price": str(base_price),
                    "variant_total": str(variant_total),
                    "addon_total": str(addon_total),
                    "added_total": str(added_total),
                    "line_total": str(line_total),
                },
                "quantity": qty,
                "variants": [
                    {
                        "option_id": v.id,
                        "group_id": v.group_id,
                        "group_name": v.group.name,
                        "option_name": v.name,
                        "price_diff": str(v.price_diff),
                    }
                    for v in chosen_variants
                ],
                "addons": [
                    {
                        "addon_id": a.id,
                        "name": a.base_item.name,
                        "price": str(a.price),
                    }
                    for a in chosen_addons
                ],
            }

            order_items_to_create.append(
                OrderItem(
                    order=order,
                    menu_item=menu_item,
                    quantity=qty,
                    price=base_price,
                    added_total=added_total,
                    line_total=line_total,
                    snapshot=snapshot,
                )
            )

        created_items = OrderItem.objects.bulk_create(order_items_to_create)

        # M2M: variants.
        variant_through = OrderItem.variants.through
        variant_links = [
            variant_through(orderitem_id=oi.id, variantoption_id=v.id)
            for oi, entry in zip(created_items, items)
            for v in entry["_variants"]
        ]
        if variant_links:
            variant_through.objects.bulk_create(variant_links)

        # M2M: addons.
        addon_through = OrderItem.addons.through
        addon_links = [
            addon_through(orderitem_id=oi.id, menuitemaddon_id=a.id)
            for oi, entry in zip(created_items, items)
            for a in entry["_addons"]
        ]
        if addon_links:
            addon_through.objects.bulk_create(addon_links)

        # Apply coupon or just recalculate totals.
        if coupon:
            applied = CouponService.apply_coupon_to_order(
                coupon, order, wallet_entry=wallet_entry
            )
            if not applied:
                raise serializers.ValidationError(
                    {"coupon_code": "Coupon is not valid for this order."}
                )
        else:
            CouponService.recalculate_totals(order)

        return order, phrase
