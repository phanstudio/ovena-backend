import pytest
from decimal import Decimal
from django.db import IntegrityError
from accounts.models import Restaurant
from menu.models import (
    Menu, MenuCategory, MenuItem, VariantGroup, VariantOption,
    MenuItemAddonGroup, MenuItemAddon, MenuItemAvailability
)

@pytest.mark.django_db
class TestBasicMenuModels:
    """Test basic functionality of menu models"""

    def test_menu_creation_and_str(self, restaurant):
        """Test basic menu creation and string representation"""
        menu = Menu.objects.create(
            restaurant=restaurant,
            name="Breakfast Menu",
            description="Morning specials",
            is_active=True
        )
        
        assert str(menu) == f"{restaurant.company_name} - Breakfast Menu"
        assert menu.is_active is True
        assert menu.restaurant == restaurant

    def test_menu_category_ordering(self, menu):
        """Test that menu categories are ordered by sort_order"""
        # Create categories with different sort orders
        desserts = MenuCategory.objects.create(
            menu=menu,
            name="Desserts",
            sort_order=3
        )
        appetizers = MenuCategory.objects.create(
            menu=menu,
            name="Appetizers",
            sort_order=1
        )
        mains = MenuCategory.objects.create(
            menu=menu,
            name="Main Course",
            sort_order=2
        )
        
        # Get categories and check ordering
        categories = list(MenuCategory.objects.filter(menu=menu))
        assert categories[0] == appetizers  # sort_order=1
        assert categories[1] == mains       # sort_order=2
        assert categories[2] == desserts    # sort_order=3

    def test_menu_item_creation(self, menu):
        """Test menu item creation with all fields"""
        category = MenuCategory.objects.create(
            menu=menu,
            name="Burgers",
            sort_order=1
        )
        
        item = MenuItem.objects.create(
            category=category,
            name="Classic Cheeseburger",
            description="Beef patty with cheese, lettuce, tomato",
            price=Decimal('12.99'),
            is_available=True
        )
        
        assert str(item) == "Classic Cheeseburger"
        assert item.price == Decimal('12.99')
        assert item.is_available is True
        assert item.category == category

    def test_menu_category_str_representation(self, menu):
        """Test MenuCategory string representation"""
        category = MenuCategory.objects.create(
            menu=menu,
            name="Test Category",
            sort_order=1
        )
        
        assert str(category) == f"{menu.name} - Test Category"


@pytest.mark.django_db
class TestComplexMenuStructure:
    """Test complex menu structures with multiple levels"""

    def test_multi_level_menu_structure(self, lunch_menu):
        """Test creating a complex menu with multiple categories and items"""
        # Create categories for lunch menu
        appetizers = MenuCategory.objects.create(
            menu=lunch_menu,
            name="Appetizers",
            sort_order=1
        )
        
        mains = MenuCategory.objects.create(
            menu=lunch_menu,
            name="Main Courses",
            sort_order=2
        )
        
        desserts = MenuCategory.objects.create(
            menu=lunch_menu,
            name="Desserts",
            sort_order=3
        )
        
        # Create items for each category
        caesar_salad = MenuItem.objects.create(
            category=appetizers,
            name="Caesar Salad",
            description="Fresh romaine with parmesan and croutons",
            price=Decimal('8.99')
        )
        
        pasta = MenuItem.objects.create(
            category=mains,
            name="Chicken Alfredo",
            description="Grilled chicken with fettuccine alfredo",
            price=Decimal('16.99')
        )
        
        tiramisu = MenuItem.objects.create(
            category=desserts,
            name="Tiramisu",
            description="Classic Italian dessert",
            price=Decimal('6.99')
        )
        
        # Test relationships
        assert lunch_menu.categories.count() == 3
        assert appetizers.items.count() == 1
        assert mains.items.count() == 1
        assert desserts.items.count() == 1
        
        # Test menu access through relationships
        menu_items = MenuItem.objects.filter(category__menu=lunch_menu)
        assert menu_items.count() == 3

    def test_inactive_menu_handling(self, restaurant):
        """Test handling of inactive menus"""
        inactive_menu = Menu.objects.create(
            restaurant=restaurant,
            name="Seasonal Menu",
            description="Winter specials",
            is_active=False
        )
        
        category = MenuCategory.objects.create(
            menu=inactive_menu,
            name="Winter Specials",
            sort_order=1
        )
        
        unavailable_item = MenuItem.objects.create(
            category=category,
            name="Hot Chocolate",
            description="Rich hot chocolate",
            price=Decimal('4.99'),
            is_available=False
        )
        
        assert inactive_menu.is_active is False
        assert unavailable_item.is_available is False


@pytest.mark.django_db
class TestVariantSystem:
    """Test the variant system for menu items"""

    @pytest.fixture
    def pizza_item(self, lunch_menu):
        """Create a pizza item for variant testing"""
        category = MenuCategory.objects.create(
            menu=lunch_menu,
            name="Pizza",
            sort_order=1
        )
        
        return MenuItem.objects.create(
            category=category,
            name="Margherita Pizza",
            description="Fresh mozzarella and basil",
            price=Decimal('14.99')
        )

    def test_variant_groups_and_options(self, pizza_item):
        """Test variant groups and options for menu items"""
        # Create size variant group
        size_group = VariantGroup.objects.create(
            item=pizza_item,
            name="Size",
            is_required=True
        )
        
        # Create size options
        small = VariantOption.objects.create(
            group=size_group,
            name="Small (10\")",
            price_diff=Decimal('-2.00')
        )
        
        medium = VariantOption.objects.create(
            group=size_group,
            name="Medium (12\")",
            price_diff=Decimal('0.00')
        )
        
        large = VariantOption.objects.create(
            group=size_group,
            name="Large (14\")",
            price_diff=Decimal('3.00')
        )
        
        # Create crust variant group
        crust_group = VariantGroup.objects.create(
            item=pizza_item,
            name="Crust",
            is_required=True
        )
        
        thin_crust = VariantOption.objects.create(
            group=crust_group,
            name="Thin Crust",
            price_diff=Decimal('0.00')
        )
        
        thick_crust = VariantOption.objects.create(
            group=crust_group,
            name="Thick Crust",
            price_diff=Decimal('1.50')
        )
        
        # Test relationships and data
        assert pizza_item.variant_groups.count() == 2
        assert size_group.options.count() == 3
        assert crust_group.options.count() == 2
        
        # Test price calculations
        base_price = pizza_item.price
        small_thin_price = base_price + small.price_diff + thin_crust.price_diff
        large_thick_price = base_price + large.price_diff + thick_crust.price_diff
        
        assert small_thin_price == Decimal('12.99')
        assert large_thick_price == Decimal('19.49')

    def test_multiple_variant_groups(self, pizza_item):
        """Test item with multiple variant groups"""
        # Size variants
        size_group = VariantGroup.objects.create(
            item=pizza_item,
            name="Size",
            is_required=True
        )
        
        # Crust variants
        crust_group = VariantGroup.objects.create(
            item=pizza_item,
            name="Crust Type",
            is_required=False
        )
        
        # Cheese variants
        cheese_group = VariantGroup.objects.create(
            item=pizza_item,
            name="Cheese Amount",
            is_required=False
        )
        
        assert pizza_item.variant_groups.count() == 3
        
        # Test required vs optional groups
        required_groups = pizza_item.variant_groups.filter(is_required=True)
        optional_groups = pizza_item.variant_groups.filter(is_required=False)
        
        assert required_groups.count() == 1
        assert optional_groups.count() == 2


@pytest.mark.django_db
class TestAddonSystem:
    """Test the addon system for menu items"""

    @pytest.fixture
    def burger_item(self, lunch_menu):
        """Create a burger item for addon testing"""
        category = MenuCategory.objects.create(
            menu=lunch_menu,
            name="Burgers",
            sort_order=1
        )
        
        return MenuItem.objects.create(
            category=category,
            name="Classic Burger",
            description="Beef patty with standard toppings",
            price=Decimal('12.99')
        )

    def test_addon_groups_and_addons(self, burger_item):
        """Test addon groups and addons for menu items"""
        # Create required addon group (cheese selection)
        cheese_group = MenuItemAddonGroup.objects.create(
            item=burger_item,
            name="Cheese Selection",
            is_required=True,
            max_selection=1
        )
        
        # Create cheese options
        no_cheese = MenuItemAddon.objects.create(
            group=cheese_group,
            name="No Cheese",
            price=Decimal('0.00')
        )
        
        american_cheese = MenuItemAddon.objects.create(
            group=cheese_group,
            name="American Cheese",
            price=Decimal('1.00')
        )
        
        swiss_cheese = MenuItemAddon.objects.create(
            group=cheese_group,
            name="Swiss Cheese",
            price=Decimal('1.50')
        )
        
        # Create optional addon group (extras)
        extras_group = MenuItemAddonGroup.objects.create(
            item=burger_item,
            name="Extras",
            is_required=False,
            max_selection=0  # unlimited
        )
        
        # Create extra options
        bacon = MenuItemAddon.objects.create(
            group=extras_group,
            name="Bacon",
            price=Decimal('2.50')
        )
        
        avocado = MenuItemAddon.objects.create(
            group=extras_group,
            name="Avocado",
            price=Decimal('2.00')
        )
        
        # Test relationships
        assert burger_item.addon_groups.count() == 2
        assert cheese_group.addons.count() == 3
        assert extras_group.addons.count() == 2
        
        # Test addon group properties
        assert cheese_group.is_required is True
        assert cheese_group.max_selection == 1
        assert extras_group.is_required is False
        assert extras_group.max_selection == 0

    def test_addon_string_representations(self, burger_item):
        """Test string representations for addon models"""
        addon_group = MenuItemAddonGroup.objects.create(
            item=burger_item,
            name="Test Addon Group",
            is_required=False
        )
        
        addon = MenuItemAddon.objects.create(
            group=addon_group,
            name="Test Addon",
            price=Decimal('2.00')
        )
        
        assert str(addon_group) == "Classic Burger - Test Addon Group"
        assert str(addon) == "Test Addon Group - Test Addon"


@pytest.mark.django_db
class TestBranchAvailability:
    """Test menu item availability across different branches"""

    def test_basic_availability(self, menu_item, branch, second_branch):
        """Test basic menu item availability across branches"""
        # Create availability for first branch (available with override price)
        availability1 = MenuItemAvailability.objects.create(
            branch=branch,
            item=menu_item,
            is_available=True,
            override_price=Decimal('10.99')
        )
        
        # Create availability for second branch (not available)
        availability2 = MenuItemAvailability.objects.create(
            branch=second_branch,
            item=menu_item,
            is_available=False
        )
        
        # Test availability settings
        assert availability1.is_available is True
        assert availability1.override_price == Decimal('10.99')
        assert availability2.is_available is False
        assert availability2.override_price is None

    def test_unique_constraint_branch_item(self, menu_item, branch):
        """Test unique constraint on branch-item combination"""
        # Create first availability record
        MenuItemAvailability.objects.create(
            branch=branch,
            item=menu_item,
            is_available=True
        )
        
        # Try to create duplicate - should raise IntegrityError
        with pytest.raises(IntegrityError):
            MenuItemAvailability.objects.create(
                branch=branch,
                item=menu_item,
                is_available=False
            )

    # def test_availability_string_representation(self, menu_item, branch):
    #     """Test string representation of availability"""
    #     # Available item
    #     available = MenuItemAvailability.objects.create(
    #         branch=branch,
    #         item=menu_item,
    #         is_available=True
    #     )
        
    #     # Unavailable item
    #     unavailable = MenuItemAvailability.objects.create(
    #         branch=branch,
    #         item=menu_item,
    #         is_available=False
    #     )
        
    #     expected_available = f"{menu_item.name} @ {branch.name} - Available"
    #     expected_unavailable = f"{menu_item.name} @ {branch.name} - Out"
        
    #     # Delete one to avoid unique constraint violation
    #     unavailable.delete()
        
    #     assert str(available) == expected_available


@pytest.mark.django_db
class TestCompleteMenuIntegration:
    """Test complete menu system integration with all components"""

    def test_complete_restaurant_menu_system(self, gourmet_restaurant, gourmet_branches):
        """Test a complete restaurant system with complex menu structure"""
        downtown_branch = gourmet_branches["downtown"]
        uptown_branch = gourmet_branches["uptown"]
        
        # Create dinner menu
        dinner_menu = Menu.objects.create(
            restaurant=gourmet_restaurant,
            name="Dinner Menu",
            description="Evening fine dining"
        )
        
        # Create main course category
        mains = MenuCategory.objects.create(
            menu=dinner_menu,
            name="Main Courses",
            sort_order=2
        )
        
        # Create complex main dish (ribeye steak)
        steak = MenuItem.objects.create(
            category=mains,
            name="Ribeye Steak",
            description="Premium ribeye steak",
            price=Decimal('28.99')
        )
        
        # Add cooking level variants
        cooking_group = VariantGroup.objects.create(
            item=steak,
            name="Cooking Level",
            is_required=True
        )
        
        rare = VariantOption.objects.create(
            group=cooking_group,
            name="Rare",
            price_diff=Decimal('0.00')
        )
        
        medium_rare = VariantOption.objects.create(
            group=cooking_group,
            name="Medium Rare",
            price_diff=Decimal('0.00')
        )
        
        well_done = VariantOption.objects.create(
            group=cooking_group,
            name="Well Done",
            price_diff=Decimal('0.00')
        )
        
        # Add side dishes as addons
        sides_group = MenuItemAddonGroup.objects.create(
            item=steak,
            name="Side Dishes",
            is_required=True,
            max_selection=2
        )
        
        mashed_potatoes = MenuItemAddon.objects.create(
            group=sides_group,
            name="Mashed Potatoes",
            price=Decimal('0.00')
        )
        
        grilled_veggies = MenuItemAddon.objects.create(
            group=sides_group,
            name="Grilled Vegetables",
            price=Decimal('2.00')
        )
        
        lobster_tail = MenuItemAddon.objects.create(
            group=sides_group,
            name="Lobster Tail",
            price=Decimal('12.00')
        )
        
        # Set different availability for each branch
        downtown_availability = MenuItemAvailability.objects.create(
            branch=downtown_branch,
            item=steak,
            is_available=True
        )
        
        uptown_availability = MenuItemAvailability.objects.create(
            branch=uptown_branch,
            item=steak,
            is_available=True,
            override_price=Decimal('26.99')  # Lower price at uptown
        )
        
        # Test the complete system
        assert dinner_menu.categories.count() == 1
        assert mains.items.count() == 1
        assert steak.variant_groups.count() == 1
        assert steak.addon_groups.count() == 1
        assert steak.branch_availabilities.count() == 2
        
        # Test cooking options
        cooking_options = cooking_group.options.all()
        assert cooking_options.count() == 3
        
        # Test side options
        side_options = sides_group.addons.all()
        assert side_options.count() == 3
        
        # Test price calculations for different combinations
        base_price = steak.price  # 28.99
        
        # Downtown branch: base price + lobster tail
        effective_price_downtown = downtown_availability.override_price or base_price
        total_with_lobster_downtown = effective_price_downtown + lobster_tail.price
        assert total_with_lobster_downtown == Decimal('40.99')
        
        # Uptown branch: override price + lobster tail
        effective_price_uptown = uptown_availability.override_price
        total_with_lobster_uptown = effective_price_uptown + lobster_tail.price
        assert total_with_lobster_uptown == Decimal('38.99')


@pytest.mark.django_db
class TestMenuQueries:
    """Test complex queries on the menu system"""

    @pytest.fixture
    def query_test_setup(self, gourmet_restaurant, gourmet_branches):
        """Set up complex test data for query testing"""
        downtown = gourmet_branches["downtown"]
        uptown = gourmet_branches["uptown"]
        
        # Create menu
        menu = Menu.objects.create(
            restaurant=gourmet_restaurant,
            name="Test Menu"
        )
        
        # Create category
        category = MenuCategory.objects.create(
            menu=menu,
            name="Test Category",
            sort_order=1
        )
        
        # Create items with different prices
        item1 = MenuItem.objects.create(
            category=category,
            name="Cheap Item",
            price=Decimal('5.00')
        )
        
        item2 = MenuItem.objects.create(
            category=category,
            name="Expensive Item",
            price=Decimal('25.00'),
            is_available=False
        )
        
        item3 = MenuItem.objects.create(
            category=category,
            name="Medium Item",
            price=Decimal('15.00')
        )
        
        return {
            "menu": menu,
            "category": category,
            "items": {"cheap": item1, "expensive": item2, "medium": item3},
            "branches": {"downtown": downtown, "uptown": uptown}
        }

    def test_query_items_by_price_range(self, query_test_setup):
        """Test querying items within a price range"""
        items = query_test_setup["items"]
        
        # Query items between $10 and $20
        items_in_range = MenuItem.objects.filter(
            price__gte=Decimal('10.00'),
            price__lte=Decimal('20.00')
        )
        
        assert items_in_range.count() == 1
        assert items_in_range.first() == items["medium"]

    def test_query_available_items_globally(self, query_test_setup):
        """Test querying globally available items"""
        items = query_test_setup["items"]
        
        available_items = MenuItem.objects.filter(is_available=True)
        assert available_items.count() == 2
        assert items["expensive"] not in available_items

    def test_query_items_with_variants(self, query_test_setup):
        """Test querying items that have variants"""
        items = query_test_setup["items"]
        cheap_item = items["cheap"]
        
        # Add variant to one item
        variant_group = VariantGroup.objects.create(
            item=cheap_item,
            name="Size"
        )
        
        # Query items with variants
        items_with_variants = MenuItem.objects.filter(
            variant_groups__isnull=False
        ).distinct()
        
        assert items_with_variants.count() == 1
        assert items_with_variants.first() == cheap_item

    def test_query_items_with_addons(self, query_test_setup):
        """Test querying items that have addon groups"""
        items = query_test_setup["items"]
        medium_item = items["medium"]
        
        # Add addon group to one item
        addon_group = MenuItemAddonGroup.objects.create(
            item=medium_item,
            name="Extras"
        )
        
        # Query items with addon groups
        items_with_addons = MenuItem.objects.filter(
            addon_groups__isnull=False
        ).distinct()
        
        assert items_with_addons.count() == 1
        assert items_with_addons.first() == medium_item

    def test_complex_branch_availability_queries(self, query_test_setup):
        """Test complex queries involving branch availability"""
        setup = query_test_setup
        items = setup["items"]
        branches = setup["branches"]
        
        # Create availability records
        MenuItemAvailability.objects.create(
            branch=branches["downtown"],
            item=items["cheap"],
            is_available=True
        )
        
        MenuItemAvailability.objects.create(
            branch=branches["downtown"],
            item=items["expensive"],
            is_available=True  # Override global unavailability
        )
        
        MenuItemAvailability.objects.create(
            branch=branches["uptown"],
            item=items["cheap"],
            is_available=False
        )
        
        # Query items available at downtown branch (considering both global and branch availability)
        downtown_available = MenuItem.objects.filter(
            branch_availabilities__branch=branches["downtown"],
            branch_availabilities__is_available=True,
            is_available=True
        )
        
        # Only cheap item should be available (expensive is globally unavailable)
        assert downtown_available.count() == 1
        assert downtown_available.first() == items["cheap"]

    def test_menu_traversal_queries(self, query_test_setup):
        """Test traversing from restaurant to all menu items"""
        setup = query_test_setup
        menu = setup["menu"]
        
        # Get all items for this restaurant
        restaurant_items = MenuItem.objects.filter(
            category__menu__restaurant=menu.restaurant
        )
        
        assert restaurant_items.count() == 3
        
        # Get items from active menus only
        active_menu_items = MenuItem.objects.filter(
            category__menu__restaurant=menu.restaurant,
            category__menu__is_active=True
        )
        
        assert active_menu_items.count() == 3  # All items since menu is active


@pytest.mark.django_db
class TestMenuPerformance:
    """Test performance-related aspects and edge cases"""

    def test_bulk_menu_creation(self, restaurant):
        """Test creating menus in bulk"""
        menus_data = [
            {"name": "Breakfast Menu", "description": "Morning specials"},
            {"name": "Lunch Menu", "description": "Midday options"},
            {"name": "Dinner Menu", "description": "Evening fine dining"},
            {"name": "Weekend Specials", "description": "Weekend only items"},
        ]
        
        menus = [
            Menu(restaurant=restaurant, **menu_data)
            for menu_data in menus_data
        ]
        
        Menu.objects.bulk_create(menus)
        
        assert Menu.objects.filter(restaurant=restaurant).count() == 4

    def test_menu_item_counting(self, lunch_menu):
        """Test counting items across categories efficiently"""
        # Create multiple categories with items
        for i in range(3):
            category = MenuCategory.objects.create(
                menu=lunch_menu,
                name=f"Category {i+1}",
                sort_order=i+1
            )
            
            # Create multiple items per category
            for j in range(5):
                MenuItem.objects.create(
                    category=category,
                    name=f"Item {j+1} in Category {i+1}",
                    price=Decimal(f'{10 + i + j}.99')
                )
        
        # Test efficient counting
        total_items = MenuItem.objects.filter(category__menu=lunch_menu).count()
        assert total_items == 15
        
        # Test counting by category
        category_counts = {}
        for category in lunch_menu.categories.all():
            category_counts[category.name] = category.items.count()
        
        assert all(count == 5 for count in category_counts.values())


# Pytest configuration and custom markers
pytestmark = pytest.mark.django_db


def test_database_transactions():
    """Test that database transactions work properly with pytest-django"""
    # This test ensures that each test runs in its own transaction
    # and that database changes don't leak between tests
    assert Restaurant.objects.count() == 0
    
    restaurant = Restaurant.objects.create(
        company_name="Transaction Test",
    )
    
    assert Restaurant.objects.count() == 1