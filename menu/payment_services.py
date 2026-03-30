from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from payments.integrations.paystack.client import PaystackClient
from payments.services.sale_service import initialize_sale


paystack_client = PaystackClient()


def initialize_paystack_transaction(amount, email):
    """
    Initialize a Paystack transaction using the unified PaystackClient.
    """
    payload = {
        "amount": round(amount * 100),  # amount in kobo (5000 = ₦50.00)
        "email": check_email_with_default(email),
    }
    return paystack_client.initialize_transaction(payload)


def initialize_order_sale(order):
    """
    Initialize a Sale for a menu order and return the Paystack payment URL + reference.
    """
    branch = order.branch
    if not branch:
        raise ValueError("Order has no branch")

    business_owner_id = None
    # primary_agent = getattr(branch, "primary_agent", None)
    # if primary_agent and primary_agent.user_id:
    #     business_owner_id = str(primary_agent.user_id)
    # else:
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

    result = initialize_sale(
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
    return result


def check_email_with_default(email: str) -> str:
    try:
        validate_email(email)
        return email
    except ValidationError:
        return settings.DEFAULT_PAYMENT_EMAIL
