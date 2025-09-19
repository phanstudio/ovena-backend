import json
import pytest
# from pathlib import Path
from rest_framework.test import APIClient
# from accounts.models import Restaurant
from django.urls import reverse

# @pytest.mark.django_db
# def test_create_restaurant(registered_restaurant):
#     assert registered_restaurant.company_name == "Burger Planet"

#     # Check menus exist
#     menus = registered_restaurant.menus.all()
#     assert menus.count() == 3

# @pytest.mark.django_db
# def test_get_menus(registered_restaurant):
#     client = APIClient()

#     url = reverse("menu-list", kwargs={"restaurant_id": registered_restaurant.pk})
#     response = client.get(url)

#     assert response.status_code == 200
#     data = response.json()
#     print(json.dumps(data, indent=2))

#     assert isinstance(data, list)
#     assert len(data) == 3
#     assert any(menu["name"] == "Breakfast Menu" for menu in data)



@pytest.mark.django_db
def test_restorder_list_view(orders_taken):
    """Searching by description should return items."""
    _, resturant_manager = orders_taken
    user, _ = resturant_manager
    client = APIClient()
    # client.force_login(user)  # logs in the fixture user
    # Authenticate manager user
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    url = reverse("restaurant-order")

    response = client.get(url)  # from cheeseburger description
    assert response.status_code == 200
    print(response)
    data = response.json()
    print(json.dumps(data, indent=1))
    # assert any("plant" in item["description"].lower() for item in data)