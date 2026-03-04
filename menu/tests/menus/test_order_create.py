import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from utils import authenticate
from coupons_discount.models import Coupons
from django.utils import timezone
from datetime import timedelta


@pytest.mark.django_db
def test_order_create_with_items(registered_restaurant, user1):
    client = APIClient()
    authenticate(client, user1)

    branch = registered_restaurant
    menu_item = (
        branch.business.menus.first()
        .categories.first()
        .items.first()
    )
    variant_option = (
        menu_item.variant_groups.first()
        .options.first()
    )

    payload = {
        "branch_id": branch.id,
        "items": [
            {"menu_item_id": menu_item.id, "quantity": 2, 
             "variant_option_ids": [variant_option.id]},
        ],
    }

    url = reverse("order")
    response = client.post(url, payload, format="json")
    print(response.json())
    assert response.status_code == 201

    order_id = response.data["order_id"]
    from menu.models import Order, OrderItem

    order = Order.objects.get(id=order_id)
    items = OrderItem.objects.filter(order=order)
    assert items.count() == 1
    assert items.first().quantity == 2
    assert order.subtotal > 0
    assert order.grand_total >= order.subtotal


@pytest.mark.django_db
def test_order_create_with_delivery_coupon(registered_restaurant, user1):
    client = APIClient()
    authenticate(client, user1)

    branch = registered_restaurant
    menu_item = (
        branch.business.menus.first()
        .categories.first()
        .items.first()
    )

    variant_option = (
        menu_item.variant_groups.first()
        .options.first()
    )

    now = timezone.now()
    coupon = Coupons.objects.create(
        code="DELIV-001",
        description="Free delivery",
        coupon_type="delivery",
        scope="business",
        business=branch.business,
        discount_type="percent",
        discount_value=0,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        is_active=True,
    )

    payload = {
        "branch_id": branch.id,
        "coupon_code": coupon.code,
        "items": [
            {"menu_item_id": menu_item.id, "quantity": 2, 
             "variant_option_ids": [variant_option.id]},
        ],
    }

    url = reverse("order")
    response = client.post(url, payload, format="json")
    print(response.json())
    assert response.status_code == 201

    order_id = response.data["order_id"]
    from menu.models import Order

    order = Order.objects.get(id=order_id)
    print(order.coupons)
    assert order.coupons_id == coupon.id
    coupon.refresh_from_db()
    assert coupon.uses_count == 1

