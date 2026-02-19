from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from utils import cprint
from accounts.models import CustomerProfile, Business, User, Branch
from menu.models import BaseItem, Menu, MenuCategory, MenuItem, Order, OrderEvent


def authenticate(client, user):
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client

@pytest.fixture
def order_context(db):
    business = Business.objects.create(business_name="Order Test Rest", bn_number="BN-ORDER-001")
    branch = Branch.objects.create(Business=business, name="Main Branch", is_active=True, is_accepting_orders=True)

    menu = Menu.objects.create(Business=business, name="Main")
    category = MenuCategory.objects.create(menu=menu, name="Meals", sort_order=1)
    base_item = BaseItem.objects.create(
        Business=business,
        name="High Value Meal",
        default_price=Decimal("6000.00"),
    )
    menu_item = MenuItem.objects.create(
        category=category,
        base_item=base_item,
        custom_name="High Value Meal",
        price=Decimal("6000.00"),
    )

    user = User.objects.create(email="order-user@example.com", name="Order User")
    CustomerProfile.objects.create(user=user)

    return {
        "branch": branch,
        "menu_item": menu_item,
        "user": user,
    }


@pytest.mark.django_db
@patch("menu.views.order.check_branch_confirmation_timeout")
@patch("menu.views.order.notify_order_created")
def test_order_create_success(notify_mock, timeout_mock, order_context):
    client = APIClient()
    authenticate(client, order_context["user"])

    payload = {
        "branch_id": order_context["branch"].id,
        "items": [
            {
                "menu_item_id": order_context["menu_item"].id,
                "quantity": 1,
                "variant_option_ids": [],
                "addon_ids": [],
            }
        ],
    }

    response = client.post(reverse("order"), payload, format="json")

    assert response.status_code == 201
    assert "order_id" in response.data
    assert "delivery_passphrase" in response.data

    order = Order.objects.get(id=response.data["order_id"])
    
    assert order.orderer_id == order_context["user"].customer_profile.id
    assert order.items.count() == 1
    assert order.subtotal == Decimal("6000.00")
    assert order.discount_total == Decimal("0")
    assert order.grand_total == Decimal("6600.00")
    assert OrderEvent.objects.filter(order=order, event_type="created").exists()

    notify_mock.assert_called_once()
    timeout_mock.apply_async.assert_called_once()

@pytest.mark.django_db
@patch("menu.views.order.check_branch_confirmation_timeout")
@patch("menu.views.order.notify_order_created")
def test_order_get_success(notify_mock, timeout_mock, order_context):
    client = APIClient()
    authenticate(client, order_context["user"])

    payload = {
        "branch_id": order_context["branch"].id,
        "items": [
            {
                "menu_item_id": order_context["menu_item"].id,
                "quantity": 1,
                "variant_option_ids": [],
                "addon_ids": [],
            }
        ],
    }

    response = client.post(reverse("order"), payload, format="json")

    assert response.status_code == 201
    assert "order_id" in response.data
    assert "delivery_passphrase" in response.data

    order_id = response.data["order_id"]
    order = Order.objects.get(id=order_id)

    resp = client.get(reverse("order-detail", args=[order_id]), format="json")
    cprint("\n", resp.data, "\n", engine_config="pp")
    assert OrderEvent.objects.filter(order=order, event_type="created").exists()

    notify_mock.assert_called_once()
    timeout_mock.apply_async.assert_called_once()

@pytest.mark.django_db
def test_order_get_list_returns_only_current_customer_orders(order_context):
    client = APIClient()
    authenticate(client, order_context["user"])

    own_order = Order.objects.create(
        orderer=order_context["user"].customer_profile,
        branch=order_context["branch"],
        delivery_secret_hash="hash-1",
        status="pending",
    )

    other_user = User.objects.create(email="other-order-user@example.com", name="Other User")
    CustomerProfile.objects.create(user=other_user)
    Order.objects.create(
        orderer=other_user.customer_profile,
        branch=order_context["branch"],
        delivery_secret_hash="hash-2",
        status="pending",
    )

    response = client.get(reverse("order"))

    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["id"] == own_order.id

