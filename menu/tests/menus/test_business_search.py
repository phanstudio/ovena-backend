from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import Branch, Business
from menu.models import (
    BaseItem,
    BaseItemAvailability,
    Menu,
    MenuCategory,
    MenuItem,
    MenuItemAddon,
    MenuItemAddonGroup,
)

USER_LAT = 6.5244
USER_LNG = 3.3792
NEAR_POINT = Point(USER_LNG, USER_LAT, srid=4326)
FAR_POINT = Point(USER_LNG + 0.05, USER_LAT + 0.05, srid=4326)  # ~7.8km away, still < 15km


def _create_business_with_branch(name="Test Kitchen", point=NEAR_POINT):
    business = Business.objects.create(business_name=name)
    branch = Branch.objects.create(
        business=business,
        name=f"{name} Main",
        location=point,
        is_active=True,
        is_accepting_orders=True,
    )
    menu = Menu.objects.create(business=business, name="Main Menu")
    category = MenuCategory.objects.create(menu=menu, name="Mains")
    return business, branch, category


def _create_item(business, category, name, price="10.00"):
    base = BaseItem.objects.create(
        business=business,
        name=name,
        default_price=Decimal(price),
    )
    item = MenuItem.objects.create(
        category=category,
        base_item=base,
        custom_name=name,
        price=Decimal(price),
    )
    return item, base


def _attach_addon(business, items, addon_name, price="2.50", addon_base=None):
    if addon_base is None:
        addon_base = BaseItem.objects.create(
            business=business,
            name=addon_name,
            default_price=Decimal(price),
        )
    addon = MenuItemAddon.objects.create(
        base_item=addon_base,
        price=Decimal(price),
    )
    for idx, item in enumerate(items):
        group = MenuItemAddonGroup.objects.create(
            item=item,
            name=f"Extras {idx}",
        )
        addon.groups.add(group)
    return addon, addon_base


def _search(query="", **extra_params):
    client = APIClient()
    params = {"lat": USER_LAT, "lng": USER_LNG}
    if query is not None:
        params["search"] = query
    params.update(extra_params)
    return client.get(reverse("business-search"), params)


@pytest.mark.django_db
def test_addon_search_in_stock_matches_business():
    business, _, category = _create_business_with_branch("Grill Spot")
    item, _ = _create_item(business, category, "Jollof Rice")
    addon, _ = _attach_addon(business, [item], "Fried Plantain")

    response = _search("Plantain")
    assert response.status_code == 200
    results = response.json()["results"]

    assert len(results) == 1
    assert results[0]["business"]["id"] == business.id
    assert results[0]["match_type"] == "addon"
    assert results[0]["total_matches"] == 1
    assert results[0]["matches"] == [
        {"id": addon.id, "name": "Fried Plantain", "type": "addon"}
    ]


@pytest.mark.django_db
def test_addon_out_of_stock_at_nearest_branch_excluded():
    business, branch, category = _create_business_with_branch("Suya House")
    item, _ = _create_item(business, category, "Beef Suya")
    _, addon_base = _attach_addon(business, [item], "Extra Pepper Sauce")

    BaseItemAvailability.objects.create(
        branch=branch,
        base_item=addon_base,
        is_available=False,
    )

    # Searching for the out-of-stock addon returns no businesses
    resp_addon = _search("Pepper Sauce")
    assert resp_addon.status_code == 200
    assert resp_addon.json()["results"] == []

    # Matching by business name still does not include the out-of-stock addon
    resp_biz = _search("Suya House")
    assert resp_biz.status_code == 200
    biz_results = resp_biz.json()["results"]
    assert len(biz_results) == 1
    assert biz_results[0]["match_type"] == "business"
    assert biz_results[0]["matches"] == []
    assert biz_results[0]["total_matches"] == 0


@pytest.mark.django_db
def test_addon_in_stock_but_sole_parent_out_of_stock_excluded():
    business, branch, category = _create_business_with_branch("Burger Hub")
    item, item_base = _create_item(business, category, "Classic Burger")
    _attach_addon(business, [item], "Cheddar Cheese")

    BaseItemAvailability.objects.create(
        branch=branch,
        base_item=item_base,
        is_available=False,
    )

    response = _search("Cheddar")
    assert response.status_code == 200
    assert response.json()["results"] == []


@pytest.mark.django_db
def test_addon_included_when_one_parent_out_of_stock_and_another_in_stock():
    business, branch, category = _create_business_with_branch("Pasta Place")
    out_item, out_base = _create_item(business, category, "Lasagna")
    in_item, _ = _create_item(business, category, "Spaghetti")
    addon, _ = _attach_addon(business, [out_item, in_item], "Garlic Bread")

    BaseItemAvailability.objects.create(
        branch=branch,
        base_item=out_base,
        is_available=False,
    )

    response = _search("Garlic")
    assert response.status_code == 200
    results = response.json()["results"]

    assert len(results) == 1
    assert results[0]["match_type"] == "addon"
    assert results[0]["total_matches"] == 1
    assert results[0]["matches"] == [
        {"id": addon.id, "name": "Garlic Bread", "type": "addon"}
    ]


@pytest.mark.django_db
def test_addon_deduplicated_per_base_item_across_multiple_addons_and_groups():
    business, _, category = _create_business_with_branch("Taco Town")
    item_a, _ = _create_item(business, category, "Chicken Taco")
    item_b, _ = _create_item(business, category, "Beef Taco")

    addon_1, addon_base = _attach_addon(business, [item_a], "Guacamole", price="1.50")
    _attach_addon(business, [item_b], "Guacamole", price="2.00", addon_base=addon_base)

    response = _search("Guacamole")
    assert response.status_code == 200
    results = response.json()["results"]

    assert len(results) == 1
    assert results[0]["match_type"] == "addon"
    assert results[0]["total_matches"] == 1
    assert results[0]["matches"] == [
        {"id": addon_1.id, "name": "Guacamole", "type": "addon"}
    ]


@pytest.mark.django_db
def test_merged_menu_item_and_addon_matches_order_cap_and_cross_dedup():
    business, _, category = _create_business_with_branch("Cheese Factory")
    item_1, _ = _create_item(business, category, "Cheese Burger")
    item_2, _ = _create_item(business, category, "Cheese Pizza")
    # Same BaseItem used as both MenuItem and MenuItemAddon -> should not duplicate
    _, shared_base = _create_item(business, category, "Cheese Dip")
    _attach_addon(business, [item_1], "Cheese Dip", addon_base=shared_base)

    addon_1, _ = _attach_addon(business, [item_1], "Extra Cheese")
    _attach_addon(business, [item_2], "Smoked Cheese")

    response = _search("Cheese")
    assert response.status_code == 200
    results = response.json()["results"]

    assert len(results) == 1
    entry = results[0]
    assert entry["match_type"] == "menu_item"
    # 3 menu items + 2 distinct addons (Cheese Dip excluded as duplicate BaseItem) = 5 total
    assert entry["total_matches"] == 5
    # Capped at MENU_MATCH_LIMIT = 3, menu items first
    assert len(entry["matches"]) == 3
    assert [m["type"] for m in entry["matches"]] == [
        "menu_item",
        "menu_item",
        "menu_item",
    ]
    assert [m["name"] for m in entry["matches"]] == [
        "Cheese Burger",
        "Cheese Pizza",
        "Cheese Dip",
    ]

    # When only 1 menu item + 1 addon match, both appear in order
    biz_2, _, cat_2 = _create_business_with_branch("Bacon Diner")
    bacon_burger, _ = _create_item(biz_2, cat_2, "Bacon Burger")
    crispy_bacon, _ = _attach_addon(biz_2, [bacon_burger], "Crispy Bacon")

    resp_2 = _search("Bacon")
    assert resp_2.status_code == 200
    res_2 = resp_2.json()["results"]
    assert len(res_2) == 1
    assert res_2[0]["match_type"] == "menu_item"
    assert res_2[0]["total_matches"] == 2
    assert res_2[0]["matches"] == [
        {"id": bacon_burger.id, "name": "Bacon Burger", "type": "menu_item"},
        {"id": crispy_bacon.id, "name": "Crispy Bacon", "type": "addon"},
    ]
    assert addon_1.id is not None


@pytest.mark.django_db
def test_multi_branch_availability_isolation():
    # Business A: addon out of stock at FAR branch, in stock at NEAR branch -> INCLUDED
    biz_a, near_a, cat_a = _create_business_with_branch("Near In Stock", point=NEAR_POINT)
    far_a = Branch.objects.create(
        business=biz_a,
        name="Far Branch A",
        location=FAR_POINT,
        is_active=True,
        is_accepting_orders=True,
    )
    item_a, _ = _create_item(biz_a, cat_a, "Bowl")
    addon_a, addon_base_a = _attach_addon(biz_a, [item_a], "Truffle Oil")
    BaseItemAvailability.objects.create(
        branch=far_a,
        base_item=addon_base_a,
        is_available=False,
    )

    # Business B: addon out of stock at NEAR branch, in stock at FAR branch -> EXCLUDED
    biz_b, near_b, cat_b = _create_business_with_branch("Near Out Of Stock", point=NEAR_POINT)
    Branch.objects.create(
        business=biz_b,
        name="Far Branch B",
        location=FAR_POINT,
        is_active=True,
        is_accepting_orders=True,
    )
    item_b, _ = _create_item(biz_b, cat_b, "Pasta")
    _, addon_base_b = _attach_addon(biz_b, [item_b], "Truffle Butter")
    BaseItemAvailability.objects.create(
        branch=near_b,
        base_item=addon_base_b,
        is_available=False,
    )

    response = _search("Truffle")
    assert response.status_code == 200
    results = response.json()["results"]

    assert len(results) == 1
    assert results[0]["business"]["id"] == biz_a.id
    assert results[0]["match_type"] == "addon"
    assert results[0]["matches"] == [
        {"id": addon_a.id, "name": "Truffle Oil", "type": "addon"}
    ]
    assert near_a.id != far_a.id


@pytest.mark.django_db
def test_business_category_and_empty_search_regressions():
    biz, _, category = _create_business_with_branch("Savannah Grill")
    category.name = "Charcoal Platters"
    category.save(update_fields=["name"])
    _create_item(biz, category, "Mixed Meat")

    # Business-name match
    resp_name = _search("Savannah")
    assert resp_name.status_code == 200
    res_name = resp_name.json()["results"]
    assert len(res_name) == 1
    assert res_name[0]["match_type"] == "business"
    assert res_name[0]["matches"] == []
    assert res_name[0]["total_matches"] == 0

    # Category-name match
    resp_cat = _search("Charcoal")
    assert resp_cat.status_code == 200
    res_cat = resp_cat.json()["results"]
    assert len(res_cat) == 1
    assert res_cat[0]["match_type"] == "business"
    assert res_cat[0]["matches"] == []
    assert res_cat[0]["total_matches"] == 0

    # Empty search returns nearby business normally
    resp_empty = _search("")
    assert resp_empty.status_code == 200
    res_empty = resp_empty.json()["results"]
    assert len(res_empty) == 1
    assert res_empty[0]["business"]["id"] == biz.id
    assert res_empty[0]["match_type"] == "business"
    assert res_empty[0]["matches"] == []
    assert res_empty[0]["total_matches"] == 0
