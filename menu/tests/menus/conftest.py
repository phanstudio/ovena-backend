import json
import pytest
from pathlib import Path
from rest_framework.test import APIClient
from accounts.models import Restaurant, Address, Branch, User, PrimaryAgent, LinkedStaff, DriverProfile, CustomerProfile
from addresses.utils.gis_point import make_point
from django.urls import reverse
from menu.models import Order, OrderItem
from menu import models

# we remove availability only 
@pytest.fixture(scope="session")
def restaurant_payload():
    """Load raw restaurant JSON from file."""
    data_path = Path(__file__).parent / "data" / "new_payload.json"
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

@pytest.fixture
def driverUser(db):
    user = User.objects.create(
        email="ajugajosh@gmail.com",
        name="josh",
        role="driver"
    )
    driver = DriverProfile.objects.create(
        user=user,
        nin="78987654347",
        driver_license="678hjs",
        plate_number="98hyY68",
        vehicle_type="ke-ke",
        photo="http://example.com/img/cheeseburger.png"
    )
    return driver

@pytest.fixture
def user1(db):
    user = User.objects.create(
        email="ajugasusii@gmail.com",
        name="susii",
    )
    CustomerProfile.objects.create(
        user=user
    )
    return user

@pytest.fixture
def orders_taken(db, resturant_manager, driverUser, user1):
    """Create an order with a menu item attached."""
    _, branch, _ = resturant_manager
    menu_item = branch.restaurant.menus.first().categories.first().items.first()

    order = Order.objects.create(
        driver=driverUser,
        branch=branch,
        orderer=user1.customer_profile,
    )
    OrderItem.objects.create(
        order=order,
        menu_item=menu_item,
    )
    return order

@pytest.fixture
def registered_branch(db, registered_restaurant):
    """Create restaurant + register its menus via API."""
    addresss = Address.objects.create(
        address="10 Downing St",
        location=make_point(-0.1278, 51.5074),
    )
    branch = Branch.objects.create(
        phone_number = "08140147868",
        name="Ikeja branch",
        restaurant=registered_restaurant,
        location=addresss
    )

    return branch  # DB object, now with menus

@pytest.fixture
def resturant_manager(db, registered_branch):
    user = User.objects.create(
        email="ajugapeterben@gmail.com",
        name="ben",
        role="restaurantstaff"
    )
    pa = PrimaryAgent.objects.create(
        branch=registered_branch,
        user=user
    )
    return user, registered_branch, pa

@pytest.fixture
def linkedstaff(db, resturant_manager):
    _, _, pa = resturant_manager
    linkeduser=LinkedStaff.objects.create(
        device_name="dyukljhgf4567890",
        created_by=pa,
    )
    return linkeduser
