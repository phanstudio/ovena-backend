from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import Restaurant
from menu.models import Menu, MenuCategory, MenuItem, BaseItem

from .models import Coupons, CouponWheel
from .serializers import CouponCreateUpdateSerializer, CouponSerializer, CouponWheelSetSerializer


@pytest.fixture
def restaurant(db):
    return Restaurant.objects.create(company_name="Test Restaurant", bn_number="BN-123")


@pytest.fixture
def menu_item(db, restaurant):
    menu = Menu.objects.create(restaurant=restaurant, name="Main")
    category = MenuCategory.objects.create(menu=menu, name="Burgers")
    base_item = BaseItem.objects.create(
        restaurant=restaurant,
        name="Burger Base",
        default_price=10,
    )
    return MenuItem.objects.create(
        category=category,
        base_item=base_item,
        custom_name="Cheese Burger",
        price=12,
    )


def create_coupon(**kwargs):
    now = timezone.now()
    defaults = {
        "code": "CODE-001",
        "description": "",
        "coupon_type": "delivery",
        "scope": "global",
        "restaurant": None,
        "discount_type": "percent",
        "discount_value": 10,
        "valid_from": now - timedelta(days=1),
        "valid_until": now + timedelta(days=1),
        "is_active": True,
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
def test_coupon_create_serializer_rejects_invalid_date_order(restaurant):
    now = timezone.now()
    data = {
        "code": "DATE-001",
        "coupon_type": "delivery",
        "scope": "restaurant",
        "restaurant": restaurant.id,
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
def test_coupon_create_serializer_global_clears_restaurant(restaurant):
    now = timezone.now()
    data = {
        "code": "GLOBAL-001",
        "coupon_type": "delivery",
        "scope": "global",
        "restaurant": restaurant.id,
        "discount_type": "percent",
        "discount_value": 10,
        "valid_from": now,
        "valid_until": now + timedelta(days=1),
        "is_active": True,
    }
    serializer = CouponCreateUpdateSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["restaurant"] is None


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
