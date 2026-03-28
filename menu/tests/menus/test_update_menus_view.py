from decimal import Decimal

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.services.profiles import PROFILE_BUSINESS_ADMIN
from menu.models import (
    BaseItem,
    BaseItemAvailability,
    Menu,
    MenuCategory,
    MenuItem,
    MenuItemAddon,
    MenuItemAddonGroup,
    VariantGroup,
    VariantOption,
)
from menu.views.registration import UpdateMenusView


def _patch_update_menus(user, payload):
    request = APIRequestFactory().patch("/menus/update/", payload, format="json")
    force_authenticate(request, user=user, token={"active_profile": PROFILE_BUSINESS_ADMIN})
    response = UpdateMenusView.as_view()(request)
    response.render()
    return response


def _seed_existing_menu_tree(business):
    menu = Menu.objects.create(
        business=business,
        name="Main Menu",
        description="Original menu description",
        is_active=True,
    )
    burgers = MenuCategory.objects.create(menu=menu, name="Burgers", sort_order=1)
    drinks = MenuCategory.objects.create(menu=menu, name="Drinks", sort_order=2)

    burger_base = BaseItem.objects.create(
        business=business,
        name="Burger Base",
        description="Original burger base",
        default_price=Decimal("40.00"),
    )
    drink_base = BaseItem.objects.create(
        business=business,
        name="Cola Base",
        description="Original cola base",
        default_price=Decimal("9.00"),
    )
    cheese_base = BaseItem.objects.create(
        business=business,
        name="Cheese Base",
        description="Original cheese base",
        default_price=Decimal("4.00"),
    )

    burger_item = MenuItem.objects.create(
        category=burgers,
        base_item=burger_base,
        custom_name="Classic Burger",
        description="Juicy burger",
        price=Decimal("45.00"),
    )
    drink_item = MenuItem.objects.create(
        category=drinks,
        base_item=drink_base,
        custom_name="Cola",
        description="Cold drink",
        price=Decimal("9.50"),
    )

    variant_group = VariantGroup.objects.create(
        item=burger_item,
        name="Size",
        is_required=True,
    )
    small_option = VariantOption.objects.create(
        group=variant_group,
        name="Small",
        price_diff=Decimal("0.00"),
    )
    large_option = VariantOption.objects.create(
        group=variant_group,
        name="Large",
        price_diff=Decimal("8.00"),
    )

    addon_group = MenuItemAddonGroup.objects.create(
        item=burger_item,
        name="Extras",
        is_required=False,
        max_selection=1,
    )
    addon = MenuItemAddon.objects.create(
        base_item=cheese_base,
        price=Decimal("4.50"),
    )
    addon.groups.add(addon_group)

    return {
        "menu": menu,
        "burgers": burgers,
        "drinks": drinks,
        "burger_base": burger_base,
        "drink_base": drink_base,
        "cheese_base": cheese_base,
        "burger_item": burger_item,
        "drink_item": drink_item,
        "variant_group": variant_group,
        "small_option": small_option,
        "large_option": large_option,
        "addon_group": addon_group,
        "addon": addon,
    }


@pytest.mark.django_db
def test_update_menus_view_creates_full_nested_menu_tree(resturant_manager):
    user, branch, _ = resturant_manager

    payload = {
        "menus": [
            {
                "name": "Late Night Menu",
                "description": "Served after dark",
                "is_active": True,
                "categories": [
                    {
                        "name": "Burgers",
                        "sort_order": 1,
                        "items": [
                            {
                                "custom_name": "Smash Burger",
                                "description": "Double patty burger",
                                "price": "42.50",
                                "base_item": {
                                    "name": "Smash Burger Base",
                                    "description": "Grilled beef patty",
                                    "price": "40.00",
                                    "image": "https://example.com/burger.png",
                                },
                                "variant_groups": [
                                    {
                                        "name": "Size",
                                        "is_required": True,
                                        "options": [
                                            {"name": "Single", "price_diff": "0.00"},
                                            {"name": "Double", "price_diff": "8.00"},
                                        ],
                                    }
                                ],
                                "addon_groups": [
                                    {
                                        "name": "Extras",
                                        "is_required": False,
                                        "max_selection": 2,
                                        "addons": [
                                            {
                                                "price": "5.50",
                                                "base_item": {
                                                    "name": "Cheese Slice",
                                                    "description": "Cheddar slice",
                                                    "price": "5.00",
                                                    "image": "https://example.com/cheese.png",
                                                },
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }

    response = _patch_update_menus(user, payload)

    assert response.status_code == 200
    assert response.data["message"] == "Update successful."
    assert response.data["stats"] == {
        "menus_created": 1,
        "menus_updated": 0,
        "categories_created": 1,
        "categories_updated": 0,
        "items_created": 1,
        "items_updated": 0,
        "variant_groups_created": 1,
        "variant_groups_updated": 0,
        "variant_options_created": 2,
        "variant_options_updated": 0,
        "addon_groups_created": 1,
        "addon_groups_updated": 0,
        "addons_created": 1,
        "addons_updated": 0,
    }

    menu = Menu.objects.get(business=branch.business, name="Late Night Menu")
    category = menu.categories.get(name="Burgers")
    item = category.items.get(custom_name="Smash Burger")
    variant_group = item.variant_groups.get(name="Size")
    addon_group = item.addon_groups.get(name="Extras")
    addon = addon_group.addons.get()

    assert item.base_item.name == "Smash Burger Base"
    assert item.base_item.default_price == Decimal("40.00")
    assert item.price == Decimal("42.50")
    assert list(variant_group.options.order_by("name").values_list("name", flat=True)) == ["Double", "Single"]
    assert addon.base_item.name == "Cheese Slice"
    assert addon.price == Decimal("5.50")

    availability_base_ids = set(
        BaseItemAvailability.objects.filter(branch=branch).values_list("base_item_id", flat=True)
    )
    assert availability_base_ids == {item.base_item_id, addon.base_item_id}


@pytest.mark.django_db
def test_update_menus_view_updates_existing_nodes_and_preserves_unmentioned_siblings(resturant_manager):
    user, branch, _ = resturant_manager
    setup = _seed_existing_menu_tree(branch.business)

    payload = {
        "menus": [
            {
                "id": setup["menu"].id,
                "name": "Updated Main Menu",
                "categories": [
                    {
                        "id": setup["burgers"].id,
                        "sort_order": 7,
                        "items": [
                            {
                                "id": setup["burger_item"].id,
                                "custom_name": "Deluxe Burger",
                                "price": "55.00",
                                "base_item": {
                                    "id": setup["burger_base"].id,
                                    "name": "Prime Burger Base",
                                    "price": "48.00",
                                },
                                "variant_groups": [
                                    {
                                        "id": setup["variant_group"].id,
                                        "name": "Burger Size",
                                        "options": [
                                            {
                                                "id": setup["small_option"].id,
                                                "price_diff": "1.50",
                                            }
                                        ],
                                    }
                                ],
                                "addon_groups": [
                                    {
                                        "id": setup["addon_group"].id,
                                        "max_selection": 3,
                                        "addons": [
                                            {
                                                "id": setup["addon"].id,
                                                "price": "6.50",
                                                "base_item": {
                                                    "id": setup["cheese_base"].id,
                                                    "name": "Aged Cheese Base",
                                                },
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }

    response = _patch_update_menus(user, payload)

    assert response.status_code == 200
    assert response.data["stats"] == {
        "menus_created": 0,
        "menus_updated": 1,
        "categories_created": 0,
        "categories_updated": 1,
        "items_created": 0,
        "items_updated": 1,
        "variant_groups_created": 0,
        "variant_groups_updated": 1,
        "variant_options_created": 0,
        "variant_options_updated": 1,
        "addon_groups_created": 0,
        "addon_groups_updated": 1,
        "addons_created": 0,
        "addons_updated": 1,
    }

    setup["menu"].refresh_from_db()
    setup["burgers"].refresh_from_db()
    setup["drinks"].refresh_from_db()
    setup["burger_item"].refresh_from_db()
    setup["drink_item"].refresh_from_db()
    setup["burger_base"].refresh_from_db()
    setup["cheese_base"].refresh_from_db()
    setup["variant_group"].refresh_from_db()
    setup["small_option"].refresh_from_db()
    setup["large_option"].refresh_from_db()
    setup["addon_group"].refresh_from_db()
    setup["addon"].refresh_from_db()

    assert setup["menu"].name == "Updated Main Menu"
    assert setup["burgers"].sort_order == 7
    assert setup["burger_item"].custom_name == "Deluxe Burger"
    assert setup["burger_item"].description == "Juicy burger"
    assert setup["burger_item"].price == Decimal("55.00")
    assert setup["burger_base"].name == "Prime Burger Base"
    assert setup["burger_base"].description == "Original burger base"
    assert setup["burger_base"].default_price == Decimal("48.00")
    assert setup["variant_group"].name == "Burger Size"
    assert setup["small_option"].price_diff == Decimal("1.50")
    assert setup["large_option"].price_diff == Decimal("8.00")
    assert setup["addon_group"].max_selection == 3
    assert setup["addon"].price == Decimal("6.50")
    assert setup["cheese_base"].name == "Aged Cheese Base"

    assert setup["drinks"].name == "Drinks"
    assert setup["drink_item"].custom_name == "Cola"

@pytest.mark.django_db
def test_update_menus_view_updates_bases(resturant_manager):
    user, branch, _ = resturant_manager
    setup = _seed_existing_menu_tree(branch.business)

    payload = {
        "menus": [
            {
                "id": setup["menu"].id,
                "name": "Updated Main Menu",
                "categories": [
                    {
                        "id": setup["burgers"].id,
                        "sort_order": 7,
                        "items": [
                            {
                                "id": setup["burger_item"].id,
                                "custom_name": "Deluxe Burger",
                                "price": "55.00",
                                "variant_groups": [
                                    {
                                        "id": setup["variant_group"].id,
                                        "name": "Burger Size",
                                        "options": [
                                            {
                                                "id": setup["small_option"].id,
                                                "price_diff": "1.50",
                                            }
                                        ],
                                    }
                                ],
                                "addon_groups": [
                                    {
                                        "id": setup["addon_group"].id,
                                        "max_selection": 3,
                                        "addons": [
                                            {
                                                "id": setup["addon"].id,
                                                "price": "6.50",
                                                "base_item": {
                                                    "id": setup["cheese_base"].id,
                                                    "name": "Aged Cheese Base",
                                                },
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }

    response = _patch_update_menus(user, payload)

    assert response.status_code == 200
    assert response.data["stats"] == {
        "menus_created": 0,
        "menus_updated": 1,
        "categories_created": 0,
        "categories_updated": 1,
        "items_created": 0,
        "items_updated": 1,
        "variant_groups_created": 0,
        "variant_groups_updated": 1,
        "variant_options_created": 0,
        "variant_options_updated": 1,
        "addon_groups_created": 0,
        "addon_groups_updated": 1,
        "addons_created": 0,
        "addons_updated": 1,
    }

    setup["menu"].refresh_from_db()
    setup["burgers"].refresh_from_db()
    setup["drinks"].refresh_from_db()
    setup["burger_item"].refresh_from_db()
    setup["drink_item"].refresh_from_db()
    setup["burger_base"].refresh_from_db()
    setup["cheese_base"].refresh_from_db()
    setup["variant_group"].refresh_from_db()
    setup["small_option"].refresh_from_db()
    setup["large_option"].refresh_from_db()
    setup["addon_group"].refresh_from_db()
    setup["addon"].refresh_from_db()

    print(setup["burger_base"])

    assert setup["menu"].name == "Updated Main Menu"
    assert setup["burgers"].sort_order == 7
    assert setup["burger_item"].custom_name == "Deluxe Burger"
    assert setup["burger_item"].description == "Juicy burger"
    assert setup["burger_item"].price == Decimal("55.00")
    assert setup["burger_base"].description == "Original burger base"
    assert setup["variant_group"].name == "Burger Size"
    assert setup["small_option"].price_diff == Decimal("1.50")
    assert setup["large_option"].price_diff == Decimal("8.00")
    assert setup["addon_group"].max_selection == 3
    assert setup["addon"].price == Decimal("6.50")
    assert setup["cheese_base"].name == "Aged Cheese Base"

    assert setup["drinks"].name == "Drinks"
    assert setup["drink_item"].custom_name == "Cola"



@pytest.mark.django_db
def test_update_menus_view_traverses_parents_without_counting_them_as_updates(resturant_manager):
    user, branch, _ = resturant_manager
    setup = _seed_existing_menu_tree(branch.business)

    payload = {
        "menus": [
            {
                "id": setup["menu"].id,
                "categories": [
                    {
                        "id": setup["burgers"].id,
                        "items": [
                            {
                                "id": setup["burger_item"].id,
                                "price": "49.99",
                            },
                            {
                                "custom_name": "Loaded Fries",
                                "description": "Crispy fries",
                                "base_item": {
                                    "name": "Loaded Fries Base",
                                    "description": "Potato fries",
                                    "price": "14.00",
                                },
                            },
                        ],
                    }
                ],
            }
        ]
    }

    response = _patch_update_menus(user, payload)

    assert response.status_code == 200
    assert response.data["stats"]["menus_updated"] == 0
    assert response.data["stats"]["categories_updated"] == 0
    assert response.data["stats"]["items_updated"] == 1
    assert response.data["stats"]["items_created"] == 1

    setup["menu"].refresh_from_db()
    setup["burgers"].refresh_from_db()
    setup["burger_item"].refresh_from_db()

    assert setup["menu"].name == "Main Menu"
    assert setup["burgers"].name == "Burgers"
    assert setup["burger_item"].price == Decimal("49.99")

    new_item = MenuItem.objects.get(category=setup["burgers"], custom_name="Loaded Fries")
    assert new_item.base_item.name == "Loaded Fries Base"
    assert new_item.price == Decimal("14.00")


@pytest.mark.django_db
def test_update_menus_view_reuses_existing_base_item_by_name_for_new_items(resturant_manager):
    user, branch, _ = resturant_manager
    setup = _seed_existing_menu_tree(branch.business)

    payload = {
        "menus": [
            {
                "id": setup["menu"].id,
                "categories": [
                    {
                        "id": setup["drinks"].id,
                        "items": [
                            {
                                "custom_name": "Zero Cola",
                                "description": "Sugar free",
                                "base_item": {
                                    "name": "Cola Base",
                                    "description": "Ignored because base item already exists",
                                    "price": "12.00",
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }

    response = _patch_update_menus(user, payload)

    assert response.status_code == 200
    assert response.data["stats"]["items_created"] == 1
    assert BaseItem.objects.filter(business=branch.business, name="Cola Base").count() == 1

    new_item = MenuItem.objects.get(category=setup["drinks"], custom_name="Zero Cola")
    assert new_item.base_item_id == setup["drink_base"].id
    assert new_item.price == Decimal("9.00")


@pytest.mark.django_db
def test_update_menus_view_rejects_non_list_menus_payload(resturant_manager):
    user, branch, _ = resturant_manager

    response = _patch_update_menus(user, {"menus": {"name": "not-a-list"}})

    assert response.status_code == 400
    assert response.data == {"detail": "`menus` must be a list."}
    assert Menu.objects.filter(business=branch.business).count() == 0


@pytest.mark.django_db
def test_update_menus_view_rejects_new_base_item_without_required_fields(resturant_manager):
    user, branch, _ = resturant_manager

    payload = {
        "menus": [
            {
                "name": "Broken Menu",
                "categories": [
                    {
                        "name": "Broken Category",
                        "items": [
                            {
                                "custom_name": "Broken Item",
                                "base_item": {
                                    "description": "Missing required name and price",
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }

    response = _patch_update_menus(user, payload)

    assert response.status_code == 400
    assert "name is required when creating a base item." in str(response.data)
    assert Menu.objects.filter(business=branch.business).count() == 0
    assert BaseItem.objects.filter(business=branch.business).count() == 0
