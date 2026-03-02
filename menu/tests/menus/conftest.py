import json
from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from utils import authenticate

from accounts.models import (
    Business, Address, Branch, User, PrimaryAgent, LinkedStaff,
    DriverProfile, CustomerProfile, BusinessAdmin, BusinessOnboardStatus
)
from addresses.utils.gis_point import make_point
from menu.models import Order, OrderItem



@pytest.fixture(scope="session")
def restaurant_payload():
    """Load raw business JSON from file."""
    data_path = Path(__file__).parent / "data" / "new2_payload.json"
    with data_path.open() as f:
        return json.load(f)


@pytest.fixture
def Business_obj(db):
    """Create a business in the DB (without menus)."""
    return Business.objects.create(
        business_name="Burger Planet",
        # bn_number="5678903-209"
    )


@pytest.fixture
def registered_branch(db, Business_obj):
    """Create a branch for the business."""
    # address_obj = Address.objects.create(
    #     address="10 Downing St",
    #     location=make_point(-0.1278, 51.5074),  # lon, lat
    # )

    branch = Branch.objects.create(
        # phone_number="08140147868",
        name="Ikeja branch",
        business=Business_obj,
        location=make_point(-0.1278, 51.5074),  # ✅ PointField expects a point, not Address
    )
    return branch


@pytest.fixture
def resturant_manager(db, registered_branch):
    """
    Create the user who owns/manages the branch via PrimaryAgent.
    This is the user you must authenticate as to call register-menu.
    """
    user = User.objects.create(
        email="ajugapeterben@gmail.com",
        name="ben",
        role="businessadmin",
    )
    pa = BusinessAdmin.objects.create(
        business=registered_branch.business,
        user=user,
    )

    BusinessOnboardStatus.objects.create(
        admin=pa, onboarding_step=2
    )
    return user, registered_branch, pa

@pytest.fixture
def resturant_vendor(db, registered_branch):
    """
    Create the user who owns/manages the branch via PrimaryAgent.
    This is the user you must authenticate as to call register-menu.
    """
    user = User.objects.create(
        email="ajugapeterbens@gmail.com",
        name="besn",
        role="businessadmin",
    )

    pa = PrimaryAgent.objects.create(
        branch=registered_branch,
        user=user,

    )
    return user, registered_branch, pa

@pytest.fixture
def auth_client(db, resturant_manager):
    """
    Authenticated APIClient as the PrimaryAgent user.
    """
    user, _, _ = resturant_manager
    client = APIClient()
    authenticate(client, user)
    return client


@pytest.fixture
def registered_restaurant(db, auth_client, restaurant_payload, resturant_manager):
    """
    Register menus via API as the authenticated primary agent.
    """
    url = reverse("register-menus-ob")
    response = auth_client.post(url, restaurant_payload, format="json")
    assert response.status_code == 201, response.content

    # Return the branch tied to this agent (useful for later tests)
    _, branch, _ = resturant_manager
    return branch


@pytest.fixture
def driverUser(db):
    user = User.objects.create(
        email="ajugajosh@gmail.com",
        name="josh",
        role="driver",
    )
    driver = DriverProfile.objects.create(
        user=user,
        # nin="78987654347",
        # driver_license="678hjs",
        # plate_number="98hyY68",
        vehicle_type="ke-ke",
        # photo="http://example.com/img/cheeseburger.png",
    )
    return driver


@pytest.fixture
def user1(db):
    user = User.objects.create(
        email="ajugasusii@gmail.com",
        name="susii",
    )
    address_obj = Address.objects.create(
        address="10 Downing St",
        location=make_point(34.1278, 51.5074),  # lon, lat
    )
    profile = CustomerProfile.objects.create(user=user, default_address=address_obj)
    profile.addresses.set([address_obj])
    # for f in user._meta.get_fields():
    #     print(f.name, type(f).__name__)
    # u = user#User.objects.first()

    # all field names
    # print([f.name for f in u._meta.get_fields()])

    # or everything including relations
    # print(u._meta.get_fields())
    # print(user.customer_profile)
    return user


@pytest.fixture
def orders_taken(db, registered_restaurant, resturant_manager, driverUser, user1):
    """
    Create an order with a menu item attached.
    Ensures menus exist by depending on registered_restaurant.
    """
    _, branch, _ = resturant_manager

    # assuming your register-menu created menus -> categories -> items
    menu_item = (
        branch.business.menus.first()
        .categories.first()
        .items.first()
    )

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
def linkedstaff(db, resturant_manager):
    _, _, pa = resturant_manager
    linked_user = LinkedStaff.objects.create(
        device_name="dyukljhgf4567890",
        created_by=pa,
    )
    return linked_user

