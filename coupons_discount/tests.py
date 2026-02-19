from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from django.urls import reverse

from accounts.models import Business, User, Branch
from accounts.models import CustomerProfile
from menu.models import Menu, MenuCategory, MenuItem, BaseItem, Order, OrderItem
from menu.services import CouponService

from .models import Coupons, CouponWheel
from .serializers import CouponCreateUpdateSerializer, CouponSerializer, CouponWheelSetSerializer


@pytest.fixture
def Business(db):
    return Business.objects.create(business_name="Test Business", bn_number="BN-123")


@pytest.fixture
def menu_item(db, Business):
    menu = Menu.objects.create(Business=Business, name="Main")
    category = MenuCategory.objects.create(menu=menu, name="Burgers")
    base_item = BaseItem.objects.create(
        Business=Business,
        name="Burger Base",
        default_price=10,
    )
    return MenuItem.objects.create(
        category=category,
        base_item=base_item,
        custom_name="Cheese Burger",
        price=12,
    )

@pytest.fixture
def menu_items(db, Business):
    menu = Menu.objects.create(Business=Business, name="Main")
    category = MenuCategory.objects.create(menu=menu, name="Burgers")
    base_buy = BaseItem.objects.create(
        Business=Business,
        name="Buy Item",
        default_price=10,
    )
    base_get = BaseItem.objects.create(
        Business=Business,
        name="Get Item",
        default_price=6,
    )
    buy_item = MenuItem.objects.create(
        category=category,
        base_item=base_buy,
        custom_name="Buy Item",
        price=10,
    )
    get_item = MenuItem.objects.create(
        category=category,
        base_item=base_get,
        custom_name="Get Item",
        price=6,
    )
    return buy_item, get_item


def create_coupon(**kwargs):
    now = timezone.now()
    defaults = {
        "code": "CODE-001",
        "description": "",
        "coupon_type": "delivery",
        "scope": "global",
        "Business": None,
        "discount_type": "percent",
        "discount_value": 10,
        "valid_from": now - timedelta(days=1),
        "valid_until": now + timedelta(days=1),
        "is_active": True,
        "buy_amount": 0,
        "get_amount": 0,
        "buy_item": None,
        "get_item": None,
    }
    defaults.update(kwargs)
    return Coupons.objects.create(**defaults)


@pytest.mark.django_db
def test_coupon_urls_include_public_and_admin():
    from . import urls

    routes = {pattern.pattern._route: pattern.name for pattern in urls.urlpatterns}

    assert "coupons/eligible/" in routes
    assert "coupon-wheel/" in routes
    assert "coupon-wheel/spin/" in routes

    assert "admin/coupons/" in routes
    assert "admin/coupons/<int:pk>/" in routes
    assert "admin/coupon-wheels/" in routes
    assert "admin/coupon-wheels/<int:pk>/" in routes


@pytest.mark.django_db
def test_coupon_create_serializer_rejects_invalid_date_order(Business):
    now = timezone.now()
    data = {
        "code": "DATE-001",
        "coupon_type": "delivery",
        "scope": "Business",
        "Business": Business.id,
        "discount_type": "percent",
        "discount_value": 10,
        "valid_from": now,
        "valid_until": now - timedelta(days=1),
        "is_active": True,
    }
    serializer = CouponCreateUpdateSerializer(data=data)
    assert not serializer.is_valid()
    assert "valid_until" in serializer.errors


@pytest.mark.django_db
def test_coupon_create_serializer_global_clears_restaurant(Business):
    now = timezone.now()
    data = {
        "code": "GLOBAL-001",
        "coupon_type": "delivery",
        "scope": "global",
        "Business": Business.id,
        "discount_type": "percent",
        "discount_value": 10,
        "valid_from": now,
        "valid_until": now + timedelta(days=1),
        "is_active": True,
    }
    serializer = CouponCreateUpdateSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["Business"] is None


@pytest.mark.django_db
def test_coupon_serializer_time_left_none_before_valid_from():
    now = timezone.now()
    coupon = create_coupon(
        code="FUTURE-001",
        valid_from=now + timedelta(days=1),
        valid_until=now + timedelta(days=2),
    )
    data = CouponSerializer(coupon).data
    assert data["time_left_seconds"] is None


@pytest.mark.django_db
def test_coupon_wheel_set_serializer_filters_ineligible_coupons(menu_item):
    eligible = create_coupon(code="ELIG-001")
    ineligible = create_coupon(code="INELIG-001", is_active=False)

    wheel = CouponWheel.objects.create(max_entries_amount=6, is_active=False)
    serializer = CouponWheelSetSerializer(
        instance=wheel,
        data={"coupon_ids": [eligible.id, ineligible.id]},
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()

    wheel.refresh_from_db()
    assert set(wheel.coupons.values_list("id", flat=True)) == {eligible.id}


@pytest.mark.django_db
def test_coupon_wheel_spin_picks_eligible_coupon():
    user = User.objects.create(email="wheel@example.com", name="Wheel User")
    client = APIClient()
    client.force_authenticate(user=user)

    coupon = create_coupon(code="WHEEL-001")
    wheel = CouponWheel.objects.create(max_entries_amount=6, is_active=True)
    wheel.coupons.add(coupon)

    url = reverse("coupon-wheel-spin")
    response = client.post(url)
    assert response.status_code == 200
    assert response.data["picked"]["code"] == coupon.code


@pytest.mark.django_db
def test_apply_bxgy_coupon_to_order(menu_items, Business):
    buy_item, get_item = menu_items

    branch = Branch.objects.create(Business=Business, name="Main Branch")
    user = User.objects.create(email="buyer@example.com", name="Buyer")
    customer_profile = CustomerProfile.objects.create(user=user)

    order = Order.objects.create(
        orderer=customer_profile,
        branch=branch,
        delivery_secret_hash="secret",
        status="pending",
    )

    OrderItem.objects.create(
        order=order,
        menu_item=buy_item,
        price=buy_item.price,
        quantity=2,
        line_total=buy_item.price * 2,
    )
    OrderItem.objects.create(
        order=order,
        menu_item=get_item,
        price=get_item.price,
        quantity=1,
        line_total=get_item.price * 1,
    )

    coupon = create_coupon(
        code="BXGY-001",
        coupon_type="BxGy",
        buy_amount=2,
        get_amount=1,
        buy_item=buy_item,
        get_item=get_item,
        scope="Business",
        Business=Business,
    )

    applied = CouponService.apply_coupon_to_order(coupon, order)
    assert applied is True

    order.refresh_from_db()
    assert order.coupons_id == coupon.id
    assert order.discount_total == get_item.price
    coupon.refresh_from_db()
    assert coupon.uses_count == 1

