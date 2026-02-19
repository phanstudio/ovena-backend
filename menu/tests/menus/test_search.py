import pytest
from rest_framework.test import APIClient
from django.urls import reverse
from utils import authenticate, cprint
from menu.models import MenuItemAddonGroup, VariantGroup, VariantOption


@pytest.mark.django_db
def test_search_menu_items_by_name(registered_restaurant):
    """Searching by item name should return matching results."""
    client = APIClient()
    url = reverse("menuitem-search")  # make sure this is in your urls.py

    response = client.get(url, {"q": "Cheeseburger"})
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert any("Cheeseburger" in item["custom_name"] for item in data)


@pytest.mark.django_db
def test_menu_item_list(registered_restaurant):
    """Searching by item name should return matching results."""
    client = APIClient()
    url = reverse("menu-list", args=[registered_restaurant.business_id])  # make sure this is in your urls.py

    response = client.get(url)
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert any("Cheeseburger" in item["custom_name"] for cats in data for items in cats["categories"]  for item in items["items"])


@pytest.mark.django_db
def test_homepage(registered_restaurant, user1):
    """Searching by item name should return matching results."""
    client = APIClient()
    client = authenticate(client, user1)
    url = reverse("home-page")

    response = client.get(url, {"lng": 677.9, "lat":98.9})
    assert response.status_code == 200


    # cprint([i[:1] for i in response.json().values()], engine_config="pp")
    cprint(list(response.json().values())[0][0]['menus'][0]['name'])#[:2], engine_config="pp")
    cprint(list(response.json().values())[1][0]['menus'][0]['name'])#[:2], engine_config="pp")

    data = response.json()
    assert len(data.keys()) == 3
    # assert any("Cheeseburger" in item["custom_name"] for cats in data for items in cats["categories"]  for item in items["items"])


@pytest.mark.django_db
def test_homepage_without_location(registered_restaurant, user1):
    """Searching by item name should return matching results."""
    client = APIClient()
    client = authenticate(client, user1)
    url = reverse("home-page")

    response = client.get(url)
    assert response.status_code == 200

    data = response.json()
    assert len(data.keys()) == 3


@pytest.mark.django_db
def test_groups_registered(registered_restaurant):
    """Searching by item name should return matching results."""
    cprint(list(MenuItemAddonGroup.objects.all()), engine_config="pp")
    cprint(list(VariantGroup.objects.all()), engine_config="pp")
    ...


# @pytest.mark.django_db
# def test_search_menu_items_by_description(registered_restaurant):
#     """Searching by description should return items."""
#     client = APIClient()
#     url = reverse("menuitem-search")

#     response = client.get(url, {"q": "choc"})  # from cheeseburger description
#     assert response.status_code == 200

#     data = response.json()
#     print(json.dumps(data, indent=1))
#     assert any("plant" in item["description"].lower() for item in data)


@pytest.mark.django_db
def test_search_menu_items_by_category(registered_restaurant):
    """Searching by category name should return items."""
    client = APIClient()
    url = reverse("menuitem-search")

    response = client.get(url, {"q": "Burgers"})
    assert response.status_code == 200

    data = response.json()
    assert len(data) > 0
    # cprint(data)
    # Each returned item should belong to a Burgers category
    # depends on serializer depth
    assert any("burger" in item["custom_name"].lower() for item in data)


@pytest.mark.django_db
def test_search_menu_items_by_restaurant_name(registered_restaurant):
    """Searching by Business company name should return all its items."""
    client = APIClient()
    url = reverse("menuitem-search")

    response = client.get(url, {"q": "Burger Planet"})
    assert response.status_code == 200

    data = response.json()
    assert len(data) > 0

    # cprint(data)
    # all items belong to this Business
    # serializer should include category -> menu -> Business fields
    # otherwise just check count > 0
    assert isinstance(data, list)


# @pytest.mark.django_db
# def test_search_menu_items_no_results(registered_restaurant):
#     """Query with no matches should return empty list."""
#     client = APIClient()
#     url = reverse("search-menu-items")

#     response = client.get(url, {"q": "nonexistentfood"})
#     assert response.status_code == 200

#     data = response.json()
#     assert data == []

