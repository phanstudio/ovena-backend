import logging
from django.db import transaction, IntegrityError
from django.contrib.contenttypes.models import ContentType

from points.models import PointsLedgerEntry
from payments.services.sale_service import initialize_points_sale
from menu.models import OrderStatus


logger = logging.getLogger(__name__)


class InsufficientPoints(Exception):
    pass


def get_points_balance(user, *, for_update=False):
    """
    Derives current balance from the latest ledger row for this user.
    """
    qs = PointsLedgerEntry.objects.filter(user=user).order_by("-created_at")
    if for_update:
        qs = qs.select_for_update()
    latest = qs.first()
    return latest.balance_after if latest else 0


@transaction.atomic
def pay_order_with_points(customer, order):
    """
    1. Debits the customer's points balance (idempotent, keyed to the order).
    2. Creates a unified Sale (status="paid") so refund/completion follows
       the exact same route as a Paystack order from here on -- cancel_order
       no longer needs a separate points-reversal branch.
    """
    user = customer.user
    idempotency_key = f"order_payment:{order.id}"

    existing = PointsLedgerEntry.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        logger.info("pay_order_with_points: idempotent replay for order %s", order.id)
        return existing

    order_content_type = ContentType.objects.get_for_model(order.__class__)
    balance = get_points_balance(user, for_update=True)
    amount = int(order.grand_total)  # ASSUMPTION: 1 point == 1 NGN, see earlier note

    if balance < amount:
        raise InsufficientPoints(f"Balance {balance} is less than order total {amount}")

    try:
        entry = PointsLedgerEntry.objects.create(
            user=user,
            event_type=PointsLedgerEntry.EVENT_ORDER_PAYMENT,
            points=-amount,
            balance_after=balance - amount,
            proof_content_type=order_content_type,
            proof_object_id=str(order.id),
            idempotency_key=idempotency_key,
            notes=f"Order {order.order_number} paid with points",
        )
    except IntegrityError:
        logger.warning("pay_order_with_points: idempotency race on order %s", order.id)
        return PointsLedgerEntry.objects.get(idempotency_key=idempotency_key)

    sale_result = initialize_order_points_sale(order)
    order.sale_id = sale_result["sale_id"]
    order.status = OrderStatus.PENDING
    order.save(update_fields=["sale_id", "status"])

    return entry

def initialize_order_points_sale(order):
    branch = order.branch
    if not branch:
        raise ValueError("Order has no branch")

    business_owner_id = None
    business = getattr(branch, "business", None)
    admin = getattr(business, "admin", None) if business else None
    if admin and admin.user_id:
        business_owner_id = str(admin.user_id)

    if not business_owner_id:
        raise ValueError("Branch has no business owner user")

    total_ngn = max(order.grand_total, 500)
    amount_kobo = int(total_ngn * 100)

    items_total_kobo = int(order.subtotal * 100)
    delivery_fee_kobo = int(order.delivery_price * 100)
    platform_fee_percent = float(order.ovena_commission or 5)

    return initialize_points_sale(
        payer_id=str(order.orderer.user_id),
        driver_id=str(order.driver.user_id) if order.driver_id else None,
        business_owner_id=business_owner_id,
        amount_kobo=amount_kobo,
        metadata={
            "order_id": str(order.id),
            "order_number": order.order_number,
            "split_rule": "order_v1",
            "items_total_kobo": items_total_kobo,
            "delivery_fee_kobo": delivery_fee_kobo,
            "platform_fee_type": "percent",
            "platform_fee_percent": platform_fee_percent,
            "platform_fee_fixed_kobo": 500 * 100,
        },
    )
