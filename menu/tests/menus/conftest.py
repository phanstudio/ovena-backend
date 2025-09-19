import json
import pytest
from pathlib import Path
from rest_framework.test import APIClient
from accounts.models import Restaurant, Address, Branch, User, PrimaryAgent, LinkedStaff, DriverProfile, CustomerProfile
from addresses.utils.gis_point import make_point
from django.urls import reverse
from menu.models import Order, OrderItem
from menu import models

# we romve availability only 

@pytest.fixture(scope="session")
def restaurant_payload():
    """Load raw restaurant JSON from file."""
    data_path = Path(__file__).parent / "data" / "new_payload.json"#"resturant_payload.json"
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

# photo = models.ImageField(upload_to="drivers/photos/")

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

    _, branch = resturant_manager

    # get any MenuItem from the branch
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
    return order, resturant_manager

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
    # linkeduser=LinkedStaff.objects.create(
    #     device_name="dyukljhgf4567890",
    #     created_by=pa,
    # )
    return user, registered_branch

@pytest.fixture
def linkedstaff(db, resturant_manager):
    user, branch = resturant_manager
    pa = PrimaryAgent.objects.get(
        branch=branch,
        user=user
    )
    linkeduser=LinkedStaff.objects.create(
        device_name="dyukljhgf4567890",
        created_by=pa,
    )
    return linkeduser


# @pytest.fixture
# def registered_restaurant_fast(db, restaurant_payload, restaurant):
#     """Create restaurant and menus via ORM, faster than hitting the API."""
#     from menu.models import Menu, Category, MenuItem, VariantGroup, VariantOption, MenuItemAddonGroup, MenuItemAddon, BaseItemAvailability, BaseItem

#     for menu_data in restaurant_payload["menus"]:
#         menu = Menu.objects.create(
#             restaurant=restaurant,
#             name=menu_data["name"],
#             description=menu_data.get("description", ""),
#             is_active=menu_data.get("is_active", True)
#         )

#         for cat_data in menu_data["categories"]:
#             category = Category.objects.create(
#                 menu=menu,
#                 name=cat_data["name"],
#                 sort_order=cat_data.get("sort_order", 1)
#             )

#             for item_data in cat_data["items"]:
#                 base_item = BaseItem.objects.create(
#                     name=item_data["base_item"]["name"],
#                     description=item_data["base_item"]["description"],
#                     price=item_data["base_item"]["price"]
#                 )

#                 menu_item = MenuItem.objects.create(
#                     category=category,
#                     custom_name=item_data["custom_name"],
#                     description=item_data.get("description", ""),
#                     price=item_data.get("price", 0),
#                     image=item_data.get("image", ""),
#                     base_item=base_item
#                 )

#                 for vg_data in item_data.get("variant_groups", []):
#                     vg = VariantGroup.objects.create(
#                         menu_item=menu_item,
#                         name=vg_data["name"],
#                         is_required=vg_data.get("is_required", False)
#                     )
#                     for opt in vg_data.get("options", []):
#                         VariantOption.objects.create(
#                             variant_group=vg,
#                             name=opt["name"],
#                             price_diff=opt.get("price_diff", 0)
#                         )

#                 for ag_data in item_data.get("addon_groups", []):
#                     ag = MenuItemAddonGroup.objects.create(
#                         menu_item=menu_item,
#                         name=ag_data["name"],
#                         is_required=ag_data.get("is_required", False),
#                         max_selection=ag_data.get("max_selection", 0)
#                     )
#                     for addon in ag_data.get("addons", []):
#                         addon_base = BaseItem.objects.create(
#                             name=addon["base_item"]["name"],
#                             description=addon["base_item"]["description"],
#                             price=addon["base_item"]["price"]
#                         )
#                         MenuItemAddon.objects.create(
#                             group=ag,
#                             base_item=addon_base,
#                             price=addon["price"]
#                         )

#                 # for avail in item_data.get("availabilities", []):
#                 #     Availability.objects.create(
#                 #         menu_item=menu_item,
#                 #         branch=branch if branch.name == avail["branch"] else None,
#                 #         is_available=avail.get("is_available", True),
#                 #         override_price=avail.get("override_price")
#                 #     )

#     return restaurant
