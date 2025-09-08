import json
import pytest
from pathlib import Path
from rest_framework.test import APIClient
from accounts.models import Restaurant
from django.urls import reverse

@pytest.fixture
def restaurant_payload():
    """Load raw restaurant JSON from file."""
    data_path = Path(__file__).parent / "data" / "resturant_payload.json" # restaurant_payload
    with data_path.open() as f:
        return json.load(f)

@pytest.fixture
def restaurant(db):
    """Create a restaurant in the DB (without menus)."""
    return Restaurant.objects.create(
        company_name="Burger Planet",
        bn_number="5678903-209"
    )

@pytest.fixture
def registered_restaurant(db, restaurant, restaurant_payload):
    """Create restaurant + register its menus via API."""
    client = APIClient()

    # attach the restaurant ID into payload
    restaurant_payload["restaurant_id"] = restaurant.pk

    url = reverse("register-menu")
    response = client.post(url, restaurant_payload, format="json")
    assert response.status_code == 201, response.content

    return restaurant  # DB object, now with menus

# @pytest.mark.django_db
# def test_create_restaurant(registered_restaurant):
#     assert registered_restaurant.company_name == "Burger Planet"

#     # Check menus exist
#     menus = registered_restaurant.menus.all()
#     assert menus.count() == 3

@pytest.mark.django_db
def test_get_menus(registered_restaurant):
    client = APIClient()

    url = reverse("menu-list", kwargs={"restaurant_id": registered_restaurant.pk})
    response = client.get(url)

    assert response.status_code == 200
    data = response.json()
    print(json.dumps(data, indent=2))

    assert isinstance(data, list)
    assert len(data) == 3
    assert any(menu["name"] == "Breakfast Menu" for menu in data)
