from menu.models import Coupons, Order, OrderItem
from django.utils.timezone import now
from django.db.models import Sum

class CouponService(): # does this affect the order or the order item the valid stuff affects

    @staticmethod
    def is_valid_for(coupon: Coupons, order: Order) -> bool:
        """Check if coupon is usable for a given order."""
        current_time = now()

        if not coupon.is_active:
            return False
        if coupon.valid_from > current_time or coupon.valid_until < current_time:
            return False
        if coupon.max_uses and coupon.uses_count >= coupon.max_uses:
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
            items: OrderItem = order.items.filter(menu_item_id=coupon.item_id).only("discount_amount", "price", "quantity") 

            if items:
                amount_bought = sum(i.quantity for i in items)
                
                free_count = self.calculate_free_items(amount_bought, coupon.buy_amount, coupon.free_amount)
                
                if free_count > 0:
                    item_price = items[0].price
                    remaining_free = free_count

                    updated = []

                    for i in items:
                        if remaining_free <= 0:
                            break

                        free_here = min(i.quantity, remaining_free)
                        i.discount_amount += free_here * item_price
                        remaining_free -= free_here
                        updated.append(i)

                    if updated:
                        OrderItem.objects.bulk_update(updated, ["discount_amount"])
        
        agg = order.items.aggregate(
            subtotal=Sum("line_total"),
            discount_total=Sum("discount_amount"),
        )
        subtotal = agg["subtotal"] or 0
        discount_total = agg["discount_total"] or 0

        grand_total = subtotal - discount_total
        order.subtotal = subtotal
        order.discount_total = discount_total
        order.grand_total = (
            grand_total
            + order.delivery_price
            + (grand_total * order.ovena_commision / 100.0)
        )
        order.save(update_fields=["subtotal", "discount_total", "grand_total"])
    
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
        """Calculate freebies for Buy X Get Y (with pro-rata leftover)."""
        if bought < buy_amount:
            return 0  # not enough items to trigger

        group_size = buy_amount + get_amount

        # Exact freebies from full groups
        full_groups = bought // group_size
        free = full_groups * get_amount

        # Handle leftover (partial group, pro-rata)
        leftover = bought % group_size
        # Scale proportionally: (leftover / group_size) * get_amount
        free += (leftover * get_amount) // group_size

        return free

    @staticmethod
    def apply_discount(coupon, subtotal):
        if coupon.discount_type == "percent":
            return subtotal - (subtotal * (coupon.discount_value / 100))
        return max(subtotal - coupon.discount_value, 0)
