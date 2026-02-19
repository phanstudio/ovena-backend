import pytest
from rest_framework.test import APIClient
from django.urls import reverse
from menu.models import (
    Business, Menu, MenuCategory, MenuItem, Branch, 
    MenuItemAddon, MenuItemAddonGroup, VariantGroup, VariantOption
)
from accounts.models import Address
import json

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def sample_data(db):
    # Create addresses
    addr1 = Address.objects.create(address="123 Main St", latitude=23443, longitude=67433)
    addr2 = Address.objects.create(address="456 Side St", latitude=45643, longitude=67433)

    restaurants = []
    branches = []
    menus = []
    categories = []
    items = []
    variant_groups = []
    variant_options = []
    addon_groups = []
    addons = []

    for r in range(1, 3):
        Business = Business.objects.create(business_name=f"Testaurant {r}")
        restaurants.append(Business)

        # Create branches for this Business
        branch1 = Branch.objects.create(Business=Business, name=f"Ikeja Branch {r}", location=addr1)
        branch2 = Branch.objects.create(Business=Business, name=f"Yaba Branch {r}", location=addr2)
        branches.extend([branch1, branch2])

        # Create 1 menu per Business
        menu = Menu.objects.create(
            Business=Business,
            name=f"Menu {r}",
            description=f"Specials for Business {r}"
        )
        menus.append(menu)

        # Each menu has 3 categories
        for c in range(1, 4):
            category = MenuCategory.objects.create(
                menu=menu,
                name=f"Category {c} (R{r})",
                sort_order=c
            )
            categories.append(category)

            # Each category has 4 items
            for i in range(1, 5):
                # Ensure one item has a known name for search tests
                name = "Cheeseburger" if r == 1 and c == 1 and i == 1 else f"Item {i} (C{c}, R{r})"
                item = MenuItem.objects.create(
                    category=category,
                    name=name,
                    price=round(5 + i + c + r, 2)
                )
                items.append(item)

                # --- Variants ---
                vg_size = VariantGroup.objects.create(item=item, name="Size", is_required=True)
                variant_groups.append(vg_size)
                for opt_name, price_diff in [("Small", 0), ("Medium", 2), ("Large", 4)]:
                    vo = VariantOption.objects.create(group=vg_size, name=opt_name, price_diff=price_diff)
                    variant_options.append(vo)

                vg_style = VariantGroup.objects.create(item=item, name="Style", is_required=False)
                variant_groups.append(vg_style)
                for opt_name, price_diff in [("Grilled", 1), ("Crispy", 1.5)]:
                    vo = VariantOption.objects.create(group=vg_style, name=opt_name, price_diff=price_diff)
                    variant_options.append(vo)

                # --- Addons ---
                ag_extras = MenuItemAddonGroup.objects.create(item=item, name="Extras", is_required=False, max_selection=3)
                addon_groups.append(ag_extras)
                for addon_name, addon_price in [("Cheese", 1), ("Fries", 2), ("Bacon", 2.5)]:
                    addon = MenuItemAddon.objects.create(group=ag_extras, name=addon_name, price=addon_price)
                    addons.append(addon)

    return {
        "restaurants": restaurants,
        "branches": branches,
        "menus": menus,
        "categories": categories,
        "items": items,
        "variant_groups": variant_groups,
        "variant_options": variant_options,
        "addon_groups": addon_groups,
        "addons": addons,
    }

@pytest.mark.django_db
def test_restaurant_list(api_client, sample_data):
    url = reverse("Business-list")  # depends on your urls.py
    response = api_client.get(url)

    assert response.status_code == 200
    data = response.json()
    print(json.dumps(data, indent=2))
    assert len(data) == 1
    assert data[0]["business_name"] == "Testaurant"
    assert data[0]["menus"][0]["name"] == "Lunch Menu"

@pytest.mark.django_db
def test_menu_list(api_client, sample_data):
    business_id = sample_data["Business"].id
    url = reverse("menu-list", args=[business_id])
    response = api_client.get(url)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["categories"][0]["name"] == "Burgers"

@pytest.mark.django_db
def test_search_menu_items(api_client, sample_data):
    url = reverse("menuitem-search") + "?q=cheese"
    response = api_client.get(url)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Cheeseburger"

