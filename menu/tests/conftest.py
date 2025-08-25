import pytest
from pytest_factoryboy import register
from .factory import (
    AddressFactory, RestaurantFactory, BranchFactory,
    MenuFactory, MenuCategoryFactory, MenuItemFactory,
    VariantGroupFactory, VariantOptionFactory,
    MenuItemAddonGroupFactory, MenuItemAddonFactory,
    MenuItemAvailabilityFactory
)

# Register all factories as pytest fixtures
register(AddressFactory)
register(RestaurantFactory)
register(BranchFactory)
register(MenuFactory)
register(MenuCategoryFactory)
register(MenuItemFactory)
register(VariantGroupFactory)
register(VariantOptionFactory)
register(MenuItemAddonGroupFactory)
register(MenuItemAddonFactory)
register(MenuItemAvailabilityFactory)

@pytest.fixture
def restaurant(restaurant_factory):
    """Create a test restaurant"""
    return restaurant_factory(company_name="Test Restaurant")

@pytest.fixture
def branch(branch_factory, restaurant, address_factory):
    """Create a test branch"""
    address = address_factory(address="123 Test Street")
    return branch_factory(
        restaurant=restaurant,
        location=address,
        name="Main Branch",
        phone_number="+1234567890",
    )


@pytest.fixture
def second_branch(branch_factory, restaurant, address_factory):
    """Create a second test branch"""
    address = address_factory(address="123 Test Street")
    return branch_factory(
        restaurant=restaurant,
        location=address,
        name="Second Branch",
        phone_number="+1234576890",
    )


@pytest.fixture
def menu(menu_factory, restaurant):
    """Create a basic test menu"""
    return menu_factory(
        restaurant=restaurant,
        name="Main Menu",
        description="Our main dining menu"
    )


@pytest.fixture
def lunch_menu(menu_factory, restaurant):
    """Create a lunch menu for complex testing"""
    return menu_factory(
        restaurant=restaurant,
        name="Lunch Menu",
        description="Available 11 AM - 3 PM"
    )


@pytest.fixture
def dinner_menu(menu_factory, restaurant):
    """Create a dinner menu for complex testing"""
    return menu_factory(
        restaurant=restaurant,
        name="Dinner Menu",
        description="Available 5 PM - 10 PM"
    )


@pytest.fixture
def menu_category(menu_category_factory, menu):
    """Create a test menu category"""
    return menu_category_factory(
        menu=menu,
        name="Test Category",
        sort_order=1
    )


@pytest.fixture
def menu_item(menu_item_factory, menu_category):
    """Create a test menu item"""
    return menu_item_factory(
        category=menu_category,
        name="Test Item",
        description="A test menu item",
        price="12.99"
    )

@pytest.fixture
def gourmet_restaurant(restaurant_factory):
    """Create a gourmet restaurant with complex setup"""
    return restaurant_factory(company_name="Gourmet Bistro")


@pytest.fixture
def gourmet_branches(branch_factory, gourmet_restaurant, address_factory):
    """Create multiple branches for the gourmet restaurant"""

    downtown_address = address_factory(address="456 Downtown Ave")
    uptown_address = address_factory(address="789 Uptown Blvd")

    downtown = branch_factory(
        restaurant=gourmet_restaurant,
        name="Downtown Branch",
        location=downtown_address,
        phone_number="+1234567890",
    )

    uptown = branch_factory(
        restaurant=gourmet_restaurant,
        name="Uptown Branch",
        location=uptown_address,
        phone_number="+1234568790",
    )

    return {"downtown": downtown, "uptown": uptown}
