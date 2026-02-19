import json
import pytest
from rest_framework.test import APIClient
# from accounts.models import Business
from django.urls import reverse
from authflow.services import start_time, calculate_time
from addresses.utils.gis_point import make_point
# from pathlib import Path
from accounts.models import (
    Business, Branch, Address, User, PrimaryAgent
)


# @pytest.fixture
# def restaurant_payload():
#     """Load raw Business JSON from file."""
#     data_path = Path(__file__).parent / "data" / "new_payload.json"#"resturant_payload.json" # restaurant_payload
#     with data_path.open() as f:
#         return json.load(f)

@pytest.fixture
def Business(db):
    """Create a Business in the DB (without menus)."""
    return Business.objects.create(
        business_name="Burger Planet",
        bn_number="5678903-209"
    )



@pytest.fixture
def registered_branch(db):
    """Create Business + register its menus via API."""
    Business = Business.objects.create(
        business_name="Burger Planet",
        bn_number="5678903-209"
    )
    addresss = Address.objects.create(
        address="10 Downing St",
        location=make_point(-0.1278, 51.5074),
    )
    branch = Branch.objects.create(
        phone_number = "08140147868",
        name="Ikeja branch",
        Business=Business,
        location=addresss
    )

    return branch  # DB object, now with menus

@pytest.fixture
def rUser(db):
    user = User.objects.create(
        email="ajugapeterben@gmail.com",
        name="ben"
    )
    return user

@pytest.fixture
def resturant_manager(db, registered_branch):
    user = User.objects.create(
        email="ajugapeterben@gmail.com",
        name="ben"
    )
    PrimaryAgent.objects.create(
        branch=registered_branch,
        user=user
    )
    return user


@pytest.mark.django_db
def test_reg_manager(registered_branch):
    client = APIClient()

    # Authenticate manager user
    # from rest_framework_simplejwt.tokens import RefreshToken
    # refresh = RefreshToken.for_user(resturant_manager)
    # client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    # client.force_login(rUser)  # logs in the fixture user

    st = start_time()
    url = reverse("register-rmanager")
    uname = "ben"
    response = client.post(url, {"branch_id":registered_branch.id, "email":"ajugapeterben@gmail.com", "username":uname})
    assert response.status_code == 201
    data = response.json()
    calculate_time(st)

    assert response.status_code == 201
    data = response.json()

    assert data["user"]["name"] == uname
    assert "tokens" in data


# @pytest.mark.django_db
# def test_Reg_linked_acc(resturant_manager):
#     client = APIClient()

#     # Authenticate manager user
#     from rest_framework_simplejwt.tokens import RefreshToken
#     refresh = RefreshToken.for_user(resturant_manager)
#     client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
#     # client.force_login(rUser)  # logs in the fixture user

#     st = start_time()
#     url = reverse("link-request-create")
#     response = client.post(url)
#     assert response.status_code == 200
#     data = response.json()
#     calculate_time(st)

#     st = start_time()
#     # should be in data help
#     url = reverse("link-approval")
#     device_id = "dyukljhgf4567890"
#     response = client.post(url, {"otp": data["otp"], "device_id": device_id})
#     calculate_time(st)
#     assert response.status_code == 201
#     data = response.json()

#     assert data["user"]["username"] == device_id
#     assert "tokens" in data

