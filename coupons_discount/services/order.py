from decimal import Decimal
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from coupons_discount.models import Coupons, UserCouponWallet
from menu.models import Order, OrderItem
from .helper import eligible_coupon_q


# ---------------------------------------------------------------------------
# Coupon application service
# ---------------------------------------------------------------------------

class CouponService:
    """
    Applies coupons to orders.

    Two paths:

    Marketing coupon (is_reward=False)
        - Caller resolves coupon by code.
        - apply_coupon_to_order increments uses_count at redemption.

    Reward coupon (is_reward=True)
        - Caller resolves coupon via UserCouponWallet (wallet_entry_id).
        - apply_coupon_to_order does NOT increment uses_count (already done
          at award time); instead it marks the wallet entry as used.
    """

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def is_valid_for(coupon: Coupons, order: Order) -> bool:
        """Check that the coupon can be applied to this specific order."""

        # Confirm coupon is still eligible (time window + active).
        # For reward coupons uses_count is not checked here — the wallet
        # entry is the proof of award; the coupon just needs to still be valid.
        qs = Coupons.objects.filter(pk=coupon.pk)
        if coupon.is_reward:
            # Only check time window + is_active, not uses_count cap.
            now = timezone.now()
            qs = qs.filter(
                is_active=True,
                valid_from__lte=now,
            ).filter(
                Q(valid_until__isnull=True) | Q(valid_until__gte=now)
            )
        else:
            qs = qs.filter(eligible_coupon_q())

        if not qs.exists():
            return False

        # Scope check.
        if coupon.scope == "business" and order.branch.business_id != coupon.business_id:
            return False

        # Type-specific checks.
        if coupon.coupon_type == "itemdiscount":
            return order.items.filter(menu_item_id=coupon.item_id).exists()

        if coupon.coupon_type == "categorydiscount":
            return order.items.filter(menu_item__category_id=coupon.category_id).exists()

        if coupon.coupon_type == "BxGy":
            if not coupon.buy_item_id or not coupon.get_item_id:
                return False
            return (
                order.items.filter(menu_item_id=coupon.buy_item_id).exists()
                and order.items.filter(menu_item_id=coupon.get_item_id).exists()
            )

        return True

    # ------------------------------------------------------------------
    # Top-level entry points
    # ------------------------------------------------------------------

    @staticmethod
    def apply_coupon_to_order(
        coupon: Coupons,
        order: Order,
        wallet_entry: "UserCouponWallet | None" = None,
    ) -> bool:
        """
        Validate, apply discount, and record coupon usage on an order.

        For reward coupons:  wallet_entry must be supplied and unused.
        For marketing coupons: wallet_entry must be None.

        Returns True on success, False if the coupon cannot be applied.
        """
        # Sanity-check the caller is pairing types correctly.
        if coupon.is_reward and wallet_entry is None:
            return False
        if not coupon.is_reward and wallet_entry is not None:
            return False

        if not CouponService.is_valid_for(coupon, order):
            return False

        with transaction.atomic():
            if coupon.is_reward:
                # Mark the wallet entry as used (atomically, ensure not double-spent).
                now = timezone.now()
                marked = (
                    UserCouponWallet.objects
                    .filter(pk=wallet_entry.pk, is_used=False)
                    .update(is_used=True, used_at=now)
                )
                if marked == 0:
                    return False  # already used (race condition)

            else:
                # Marketing coupon: claim one usage slot atomically.
                updated = (
                    Coupons.objects
                    .filter(pk=coupon.pk)
                    .filter(eligible_coupon_q())
                    .update(uses_count=F("uses_count") + 1)
                )
                if updated == 0:
                    return False  # coupon exhausted between validation and now

            CouponService()._apply_order_level_discount(coupon, order)
            order.coupon = coupon
            order.save(update_fields=["coupon"])

        return True

    # ------------------------------------------------------------------
    # Discount application
    # ------------------------------------------------------------------

    def _apply_order_level_discount(self, coupon: Coupons, order: Order) -> None:
        """Dispatch to the correct discount strategy and recalculate totals."""

        if coupon.coupon_type == "delivery":
            order.delivery_price = 0
            order.save(update_fields=["delivery_price"])

        elif coupon.coupon_type == "itemdiscount":
            self._apply_item_or_category_discount(
                coupon,
                order.items
                    .filter(menu_item_id=coupon.item_id)
                    .only("discount_amount", "price", "quantity"),
            )

        elif coupon.coupon_type == "categorydiscount":
            self._apply_item_or_category_discount(
                coupon,
                order.items
                    .filter(menu_item__category_id=coupon.category_id)
                    .select_related("menu_item")
                    .only("discount_amount", "price", "quantity"),
            )

        elif coupon.coupon_type == "BxGy":
            self._apply_bxgy_discount(coupon, order)

        self.recalculate_totals(order)

    def _apply_item_or_category_discount(self, coupon: Coupons, items) -> None:
        updated = []
        for item in items:
            discount_value = self.apply_discount(coupon, item.price) * item.quantity
            if discount_value > 0:
                item.discount_amount = discount_value
                updated.append(item)
        if updated:
            OrderItem.objects.bulk_update(updated, ["discount_amount"])

    def _apply_bxgy_discount(self, coupon: Coupons, order: Order) -> None:
        buy_items = order.items.filter(menu_item_id=coupon.buy_item_id).only("quantity")
        get_items = order.items.filter(menu_item_id=coupon.get_item_id).only(
            "discount_amount", "price", "quantity"
        )

        if not buy_items.exists() or not get_items.exists():
            return

        amount_bought = sum(i.quantity for i in buy_items)
        free_count = self.calculate_free_items(amount_bought, coupon.buy_amount, coupon.get_amount)

        if free_count <= 0:
            return

        remaining_free = free_count
        updated = []
        for item in get_items:
            if remaining_free <= 0:
                break
            free_here = min(item.quantity, remaining_free)
            item.discount_amount = Decimal(item.discount_amount or 0) + (
                Decimal(item.price) * free_here
            )
            remaining_free -= free_here
            updated.append(item)

        if updated:
            OrderItem.objects.bulk_update(updated, ["discount_amount"])

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_free_items(bought: int, buy_amount: int, get_amount: int) -> int:
        """Calculate freebie count for Buy X Get Y (full groups only)."""
        if bought < buy_amount:
            return 0
        full_groups = bought // buy_amount
        return full_groups * get_amount

    @staticmethod
    def apply_discount(coupon: Coupons, subtotal) -> Decimal:
        if coupon.discount_type == "percent":
            return Decimal(subtotal) * Decimal(coupon.discount_value) / Decimal("100")
        return min(Decimal(subtotal), Decimal(coupon.discount_value))

    @staticmethod
    def recalculate_totals(order: Order) -> None:
        agg = order.items.aggregate(
            subtotal=Sum("line_total"),
            discount_total=Sum("discount_amount"),
        )

        subtotal = agg["subtotal"] or Decimal("0")
        discount_total = agg["discount_total"] or Decimal("0")
        items_total = subtotal - discount_total

        grand_total = (
            items_total
            + Decimal(order.delivery_price or 0)
            + (items_total * Decimal(order.ovena_commission) / Decimal("100"))
        )

        order.subtotal = subtotal
        order.discount_total = discount_total
        order.items_total = items_total
        order.grand_total = grand_total
        order.save(update_fields=["subtotal", "discount_total", "items_total", "grand_total"])
