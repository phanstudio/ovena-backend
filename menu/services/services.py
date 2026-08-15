from coupons_discount.services import CouponService
from django.utils import timezone
from menu.models import Order, OrderStatus

# def has_20_orders_this_month(customer): 3 if they want multiple the this is fine??
#     start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
#     return Order.objects.filter(
#         orderer=customer,
#         status=OrderStatus.DELIVERED,
#         created_at__gte=start_of_month,
#     ).count() >= 20

def has_20_orders_this_month(customer):
    start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return Order.objects.filter(
        orderer=customer,
        status=OrderStatus.DELIVERED,
        created_at__gte=start_of_month,
    ).values("id")[19:20].exists()
