import factory
from decimal import Decimal
from accounts.models import Restaurant, Branch, Address
from menu.models import (
    Menu, MenuCategory, MenuItem,
    VariantGroup, VariantOption,
    MenuItemAddonGroup, MenuItemAddon,
    BaseItemAvailability
)


class AddressFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Address

    address = factory.Sequence(lambda n: f"{100+n} Test Street")
    latitude = 6.5244
    longitude = 3.3792


class RestaurantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Restaurant

    company_name = factory.Sequence(lambda n: f"Restaurant {n}")
    # email = factory.Sequence(lambda n: f"restaurant{n}@example.com")


class BranchFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Branch

    restaurant = factory.SubFactory(RestaurantFactory)
    location = factory.SubFactory(AddressFactory)
    name = factory.Sequence(lambda n: f"Branch {n}")
    phone_number = factory.Sequence(lambda n: f"+1234567{n:04d}")


class MenuFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Menu

    restaurant = factory.SubFactory(RestaurantFactory)
    name = factory.Sequence(lambda n: f"Menu {n}")
    description = "Default menu description"


class MenuCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MenuCategory

    menu = factory.SubFactory(MenuFactory)
    name = factory.Sequence(lambda n: f"Category {n}")
    sort_order = factory.Sequence(lambda n: n)


class MenuItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MenuItem

    category = factory.SubFactory(MenuCategoryFactory)
    name = factory.Sequence(lambda n: f"Item {n}")
    description = "A test menu item"
    price = Decimal("12.99")


class VariantGroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VariantGroup

    item = factory.SubFactory(MenuItemFactory)
    name = factory.Sequence(lambda n: f"Variant Group {n}")


class VariantOptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VariantOption

    group = factory.SubFactory(VariantGroupFactory)
    name = factory.Sequence(lambda n: f"Option {n}")
    price_delta = Decimal("1.00")


class MenuItemAddonGroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MenuItemAddonGroup

    item = factory.SubFactory(MenuItemFactory)
    name = factory.Sequence(lambda n: f"Addon Group {n}")


class MenuItemAddonFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MenuItemAddon

    group = factory.SubFactory(MenuItemAddonGroupFactory)
    name = factory.Sequence(lambda n: f"Addon {n}")
    price = Decimal("2.50")


class MenuItemAvailabilityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BaseItemAvailability

    item = factory.SubFactory(MenuItemFactory)
    branch = factory.SubFactory(BranchFactory)
    is_available = True
