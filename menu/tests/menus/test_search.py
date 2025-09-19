import pytest
from rest_framework.test import APIClient
from django.urls import reverse
import json


# @pytest.mark.django_db
# def test_search_menu_items_by_name(registered_restaurant):
#     """Searching by item name should return matching results."""
#     client = APIClient()
#     url = reverse("menuitem-search")  # make sure this is in your urls.py

#     response = client.get(url, {"q": "Cheeseburger"})
#     assert response.status_code == 200

#     data = response.json()
#     print(json.dumps(data, indent=1))
#     assert isinstance(data, list)
#     assert any("Cheeseburger" in item["custom_name"] for item in data)


@pytest.mark.django_db
def test_search_menu_items_by_description(registered_restaurant):
    """Searching by description should return items."""
    client = APIClient()
    url = reverse("menuitem-search")

    response = client.get(url, {"q": "choc"})  # from cheeseburger description
    assert response.status_code == 200

    data = response.json()
    print(json.dumps(data, indent=1))
    assert any("plant" in item["description"].lower() for item in data)


# @pytest.mark.django_db
# def test_search_menu_items_by_category(registered_restaurant):
#     """Searching by category name should return items."""
#     client = APIClient()
#     url = reverse("menuitem-search")

#     response = client.get(url, {"q": "Burgers"})
#     assert response.status_code == 200

#     data = response.json()
#     assert len(data) > 0
#     # Each returned item should belong to a Burgers category
#     # depends on serializer depth
#     assert any("burger" in item["custom_name"].lower() for item in data)


# @pytest.mark.django_db
# def test_search_menu_items_by_restaurant_name(registered_restaurant):
#     """Searching by restaurant company name should return all its items."""
#     client = APIClient()
#     url = reverse("menuitem-search")

#     response = client.get(url, {"q": "Burger Planet"})
#     assert response.status_code == 200

#     data = response.json()
#     assert len(data) > 0
#     # all items belong to this restaurant
#     # serializer should include category -> menu -> restaurant fields
#     # otherwise just check count > 0
#     assert isinstance(data, list)


# @pytest.mark.django_db
# def test_search_menu_items_no_results(registered_restaurant):
#     """Query with no matches should return empty list."""
#     client = APIClient()
#     url = reverse("search-menu-items")

#     response = client.get(url, {"q": "nonexistentfood"})
#     assert response.status_code == 200

#     data = response.json()
#     assert data == []
