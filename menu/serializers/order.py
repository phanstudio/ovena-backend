from decimal import Decimal
from django.db import transaction
from rest_framework import serializers
from accounts.models import Branch
from ..models import Coupons, BaseItemAvailability, MenuItem, MenuItemAddon, VariantOption, Order, OrderItem
from ..services import CouponService
from authflow.services import generate_passphrase, hash_phrase

MIN_ORDER_SUBTOTAL = Decimal("5000.00")

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
    coupon_code = serializers.CharField(required=False, allow_blank=True)
    items = OrderItemCreateSerializer(many=True)

    def validate(self, attrs):
        request = self.context["request"]
        user = self.context["user"]
        branch_id = attrs["branch_id"]
        items = attrs.get("items") or []

        # 1) Require items (placed order)
        if not items:
            raise serializers.ValidationError({"items": "An order must have at least one item."})

        # 2) Validate branch
        branch = Branch.objects.filter(id=branch_id, is_active=True).first()
        if not branch:
            raise serializers.ValidationError({"branch_id": "Invalid branch."})
        if not branch.is_accepting_orders:
            raise serializers.ValidationError({"branch_id": "This restaurant is not accepting orders right now."})
        attrs["branch"] = branch

        # 3) Coupon validation (basic)
        coupon = None
        code = (attrs.get("coupon_code") or "").strip()
        if code:
            coupon = Coupons.objects.filter(code=code).first()
            if not coupon:
                raise serializers.ValidationError({"coupon_code": "Coupon not found."})
        attrs["coupon"] = coupon

        # 4) Preload menu items (+ their base_item) in one query
        menu_item_ids = [i["menu_item_id"] for i in items]
        menu_items = (
            MenuItem.objects
            .select_related("base_item")
            .filter(id__in=menu_item_ids)
        )
        menu_map = {m.id: m for m in menu_items}
        missing = [mid for mid in menu_item_ids if mid not in menu_map]
        if missing:
            raise serializers.ValidationError({"items": f"MenuItem not found: {missing}"})

        # 5) Availability + pricing source
        # Prefer BaseItemAvailability override price for this branch.
        base_item_ids = [menu_map[mid].base_item_id for mid in menu_item_ids]
        avails = BaseItemAvailability.objects.filter(branch=branch, base_item_id__in=base_item_ids)
        avail_map = {a.base_item_id: a for a in avails}

        # 6) Preload variants/addons referenced (avoid N queries)
        all_variant_ids = set()
        all_addon_ids = set()
        for i in items:
            all_variant_ids.update(i.get("variant_option_ids") or [])
            all_addon_ids.update(i.get("addon_ids") or [])

        variant_qs = VariantOption.objects.select_related("group", "group__item").filter(id__in=all_variant_ids)
        addon_qs = MenuItemAddon.objects.prefetch_related("groups").filter(id__in=all_addon_ids)

        variant_map = {v.id: v for v in variant_qs}
        addon_map = {a.id: a for a in addon_qs}

        bad_variants = [vid for vid in all_variant_ids if vid not in variant_map]
        bad_addons = [aid for aid in all_addon_ids if aid not in addon_map]
        if bad_variants:
            raise serializers.ValidationError({"items": f"VariantOption not found: {bad_variants}"})
        if bad_addons:
            raise serializers.ValidationError({"items": f"Addon not found: {bad_addons}"})

        # 7) Validate per-item: variants/addons belong to the selected menu item,
        # required variant groups present, addon max_selection respected
        subtotal = Decimal("0.00")

        for entry in items:
            menu_item = menu_map[entry["menu_item_id"]]
            qty = int(entry["quantity"])

            # base price: branch override if exists, else menu_item.effective_price
            avail = avail_map.get(menu_item.base_item_id)
            base_price = (avail.effective_price if avail else Decimal(menu_item.effective_price))

            chosen_variant_ids = entry.get("variant_option_ids") or []
            chosen_addon_ids = entry.get("addon_ids") or []

            # --- Variants validation ---
            # All chosen variants must be for this menu_item
            chosen_variants = [variant_map[vid] for vid in chosen_variant_ids]
            for v in chosen_variants:
                if v.group.item_id != menu_item.id:
                    raise serializers.ValidationError(
                        {"items": f"VariantOption {v.id} does not belong to MenuItem {menu_item.id}."}
                    )

            # Enforce required variant groups
            required_groups = set(
                menu_item.variant_groups.filter(is_required=True).values_list("id", flat=True)
            )
            chosen_groups = {v.group_id for v in chosen_variants}
            missing_groups = required_groups - chosen_groups
            if missing_groups:
                raise serializers.ValidationError(
                    {"items": f"Missing required variant group(s) {sorted(missing_groups)} for MenuItem {menu_item.id}."}
                )

            variant_total = sum(Decimal(v.price_diff) for v in chosen_variants)

            # --- Addons validation ---
            chosen_addons = [addon_map[aid] for aid in chosen_addon_ids]

            # each addon must be connected to this item via addon_groups (their M2M groups)
            item_group_ids = set(menu_item.addon_groups.values_list("id", flat=True))
            for a in chosen_addons:
                addon_group_ids = set(a.groups.values_list("id", flat=True))
                if not (addon_group_ids & item_group_ids):
                    raise serializers.ValidationError(
                        {"items": f"Addon {a.id} is not allowed for MenuItem {menu_item.id}."}
                    )

            # max_selection per group
            # (count addons selected per group and enforce max_selection if > 0)
            counts = {gid: 0 for gid in item_group_ids}
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

            # stash computed values so create() doesn’t re-calc / re-query
            entry["_menu_item"] = menu_item
            entry["_base_price"] = base_price
            entry["_variant_total"] = variant_total
            entry["_addon_total"] = addon_total
            entry["_line_total"] = line_total
            entry["_variants"] = chosen_variants
            entry["_addons"] = chosen_addons

        # 8) Minimum subtotal before discount
        if subtotal < MIN_ORDER_SUBTOTAL:
            raise serializers.ValidationError(
                {"items": f"Minimum order subtotal is {MIN_ORDER_SUBTOTAL}. Current subtotal is {subtotal}."}
            )

        attrs["_subtotal"] = subtotal
        return attrs

    def create(self, validated_data):
        user = self.context["user"]
        branch = validated_data["branch"]
        coupon = validated_data.get("coupon")
        items = validated_data["items"]

        phrase = generate_passphrase()

        # Create order
        order = Order.objects.create(
            orderer=user.customer_profile,
            branch=branch,
            coupons=coupon,
            delivery_secret_hash=hash_phrase(phrase),
            status="pending",
        )

        # Create OrderItems in bulk
        order_items = []
        snapshots = []

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

            oi = OrderItem(
                order=order,
                menu_item=menu_item,
                quantity=qty,
                price=base_price,
                added_total=added_total,
                line_total=line_total,
                snapshot=snapshot,   # ✅ STORE SNAPSHOT HERE
            )
            order_items.append(oi)

        created_items = OrderItem.objects.bulk_create(order_items)

        # Bulk create M2M through rows (FAST)
        # variants
        variant_through = OrderItem.variants.through
        variant_links = []
        for oi, entry in zip(created_items, items):
            for v in entry["_variants"]:
                variant_links.append(variant_through(orderitem_id=oi.id, variantoption_id=v.id))
        if variant_links:
            variant_through.objects.bulk_create(variant_links)

        # addons
        addon_through = OrderItem.addons.through
        addon_links = []
        for oi, entry in zip(created_items, items):
            for a in entry["_addons"]:
                addon_links.append(addon_through(orderitem_id=oi.id, menuitemaddon_id=a.id))
        if addon_links:
            addon_through.objects.bulk_create(addon_links)

        # Apply coupon / recalc totals
        if coupon:
            applied = CouponService.apply_coupon_to_order(coupon, order)
            if not applied:
                raise serializers.ValidationError({"coupon_code": "Coupon is not valid for this order."})
        else:
            CouponService.recalculate_totals(order)

        return order, phrase
