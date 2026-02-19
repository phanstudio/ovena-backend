import json
import pytest
# from pathlib import Path
from rest_framework.test import APIClient
from menu.models import Order
from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken
from authflow.services import make_sub_token

@pytest.mark.django_db
def test_restorder_listview(orders_taken, resturant_manager, registered_restaurant):
    """Searching by description should return items."""
    user, *_ = resturant_manager
    client = APIClient()
    client = authenticate(client, user)
    url = reverse("Business-order")

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) > 0

# @pytest.mark.django_db
# def test_restorder_acceptview(orders_taken, resturant_manager):
#     """Searching by description should return items."""
#     user, *_ = resturant_manager
#     client = APIClient()
#     client = authenticate(client, user)
#     url = reverse("Business-order")

#     response = client.post(url, {"action":"accept", "order_id": orders_taken.id})
#     assert response.status_code == 202
#     orders_taken.refresh_from_db()
#     assert orders_taken.status == "confirmed"

#     response = client.post(url, {"action":"accept", "order_id": orders_taken.id})
#     assert response.status_code == 400

# @pytest.mark.django_db
# def test_restorder_cancleview(orders_taken, linkedstaff):
#     """Searching by description should return items."""
#     client = APIClient()
#     client = subauth(client, linkedstaff)
#     url = reverse("Business-order")

#     response = client.post(url, {"action": "cancle", "order_id": orders_taken.id})  # from cheeseburger description
#     assert response.status_code == 200
#     orders_taken.refresh_from_db()
#     assert orders_taken.status == "cancelled"

def authenticate(client, user):
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client

def subauth(client, linkedstaff):
    token = make_sub_token(linkedstaff.created_by.id, device_id=linkedstaff.device_name)
    client.credentials(HTTP_AUTHORIZATION=f"SubBearer {token}")
    return client


# @pytest.mark.django_db
# def test_create_restaurant(registered_restaurant):
#     assert registered_restaurant.business_name == "Burger Planet"

#     # Check menus exist
#     menus = registered_restaurant.menus.all()
#     assert menus.count() == 3

# @pytest.mark.django_db
# def test_get_menus(registered_restaurant):
#     client = APIClient()

#     url = reverse("menu-list", kwargs={"business_id": registered_restaurant.pk})
#     response = client.get(url)

#     assert response.status_code == 200
#     data = response.json()
#     print(json.dumps(data, indent=2))

#     assert isinstance(data, list)
#     assert len(data) == 3
#     assert any(menu["name"] == "Breakfast Menu" for menu in data)

