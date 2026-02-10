from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from coupons_discount.models import Coupons
from coupons_discount.services import eligible_coupon_q
from menu.models import Order, OrderItem

class CouponService(): # does this affect the order or the order item the valid stuff affects

    @staticmethod
    def is_valid_for(coupon: Coupons, order: Order) -> bool:
        """Check if coupon is usable for a given order."""
        if not Coupons.objects.filter(pk=coupon.pk).filter(eligible_coupon_q()).exists():
            return False

        # scope check (order-level)
        if coupon.scope == "restaurant" and order.branch.restaurant_id != coupon.restaurant_id:
            return False

        # item-level
        if coupon.coupon_type == "itemdiscount":
            return order.items.filter(menu_item_id=coupon.item_id).exists()

        # category-level
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
    
    def apply_order_level_discount(self, coupon: Coupons, order:Order):
        if coupon.coupon_type == "delivery":
            order.delivery_price = 0
            order.save(update_fields=["delivery_price"])
        
        elif coupon.coupon_type == "itemdiscount":
            self._apply_item_or_category_discount(
                order.items.filter(menu_item_id=coupon.item_id).only("discount_amount", "price", "quantity")
            ) 
        
        elif coupon.coupon_type == "categorydiscount":
            self._apply_item_or_category_discount(
                order.items.filter(menu_item__category_id=coupon.category_id)
                .select_related("menu_item")  # JOIN instead of N+1
                .only("discount_amount", "price", "quantity")
            )        
        
        elif coupon.coupon_type == "BxGy":
            buy_items = order.items.filter(menu_item_id=coupon.buy_item_id).only("quantity")
            get_items = order.items.filter(menu_item_id=coupon.get_item_id).only("discount_amount", "price", "quantity")

            if buy_items and get_items:
                amount_bought = sum(i.quantity for i in buy_items)
                free_count = self.calculate_free_items(amount_bought, coupon.buy_amount, coupon.get_amount)

                if free_count > 0:
                    remaining_free = free_count
                    updated = []

                    for i in get_items:
                        if remaining_free <= 0:
                            break

                        free_here = min(i.quantity, remaining_free)
                        i.discount_amount = Decimal(i.discount_amount or 0) + (Decimal(i.price) * free_here)
                        remaining_free -= free_here
                        updated.append(i)

                    if updated:
                        OrderItem.objects.bulk_update(updated, ["discount_amount"])
        
        self.recalculate_totals(order)
    
    def _apply_item_or_category_discount(self, items:OrderItem, coupon:Coupons):
        updated = []
        for i in items:
            discount_value = self.apply_discount(coupon, i.price) * i.quantity
            if discount_value > 0:
                i.discount_amount = discount_value
                updated.append(i)

        if updated:
            OrderItem.objects.bulk_update(updated, ["discount_amount"])
    
    @staticmethod
    def calculate_free_items(bought: int, buy_amount: int, get_amount: int) -> int:
        """Calculate freebies for Buy X Get Y (full groups only)."""
        if bought < buy_amount:
            return 0  # not enough items to trigger

        group_size = buy_amount + get_amount

        # Exact freebies from full groups
        full_groups = bought // buy_amount
        return full_groups * get_amount

    @staticmethod
    def apply_discount(coupon, subtotal):
        if coupon.discount_type == "percent":
            return (Decimal(subtotal) * Decimal(coupon.discount_value) / Decimal("100"))
        return min(Decimal(subtotal), Decimal(coupon.discount_value))

    @staticmethod
    def recalculate_totals(order: Order):
        agg = order.items.aggregate(
            subtotal=Sum("line_total"),
            discount_total=Sum("discount_amount"),
        )
        subtotal = agg["subtotal"] or Decimal("0")
        discount_total = agg["discount_total"] or Decimal("0")

        grand_total = Decimal(subtotal) - Decimal(discount_total)
        order.subtotal = subtotal
        order.discount_total = discount_total
        order.grand_total = (
            grand_total
            + Decimal(order.delivery_price or 0)
            + (grand_total * Decimal(order.ovena_commission) / Decimal("100.0"))
        )
        order.save(update_fields=["subtotal", "discount_total", "grand_total"])

    @staticmethod
    def apply_coupon_to_order(coupon: Coupons, order: Order):
        if not CouponService.is_valid_for(coupon, order):
            return False

        with transaction.atomic():
            updated = (
                Coupons.objects
                .filter(pk=coupon.pk)
                .filter(eligible_coupon_q())
                .update(uses_count=F("uses_count") + 1)
            )
            if updated == 0:
                return False

            CouponService().apply_order_level_discount(coupon, order)
            order.coupons = coupon
            order.save(update_fields=["coupons"])

        return True
