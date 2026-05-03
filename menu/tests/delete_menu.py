from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from accounts.models import BusinessAdmin, Business, Branch
from menu.models import (
    Menu,
    MenuCategory,
    MenuItem,
    VariantGroup,
    VariantOption,
    MenuItemAddonGroup,
    MenuItemAddon,
    BaseItem,
    BaseItemAvailability,
)
from rest_framework_simplejwt.tokens import AccessToken
from authflow.authentication import PROFILE_BUSINESS_ADMIN

User = get_user_model()


class DeleteMenuViewsTestCase(APITestCase):
    def setUp(self):
        # ─────────────────────────────
        # User / Business
        # ─────────────────────────────
        self.user = User.objects.create_user(
            email="admin@test.com",
            password="password123",
        )

        self.business = Business.objects.create(
            business_name="Test Business"
        )

        self.business_admin = BusinessAdmin.objects.create(
            user=self.user,
            business=self.business,
        )

        # self.client.force_authenticate(user=self.user)
        token = AccessToken.for_user(self.user)
        token["active_profile"] = PROFILE_BUSINESS_ADMIN

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(token)}")

        # ─────────────────────────────
        # Branch (FIXED)
        # ─────────────────────────────
        self.branch = Branch.objects.create(
            business=self.business,
            name="Main Branch"
        )

        # ─────────────────────────────
        # Menu Structure
        # ─────────────────────────────
        self.menu = Menu.objects.create(
            business=self.business,
            name="Main Menu",
        )

        self.category = MenuCategory.objects.create(
            menu=self.menu,
            name="Burgers",
        )

        # ─────────────────────────────
        # Base Items
        # ─────────────────────────────
        self.item_base = BaseItem.objects.create(
            business=self.business,
            name="Burger",
            default_price=100
        )

        self.addon_base = BaseItem.objects.create(
            business=self.business,
            name="Cheese",
            default_price=50
        )

        # FIXED: branch required + correct related name
        BaseItemAvailability.objects.create(
            branch=self.branch,
            base_item=self.item_base
        )

        BaseItemAvailability.objects.create(
            branch=self.branch,
            base_item=self.addon_base
        )

        # ─────────────────────────────
        # Menu Item (FIXED: price required)
        # ─────────────────────────────
        self.menu_item = MenuItem.objects.create(
            category=self.category,
            base_item=self.item_base,
            custom_name="Classic Burger",
            price=1500
        )

        # ─────────────────────────────
        # Variant Group / Option
        # ─────────────────────────────
        self.variant_group = VariantGroup.objects.create(
            item=self.menu_item,
            name="Size",
        )

        # FIXED: price_diff instead of price
        self.variant_option = VariantOption.objects.create(
            group=self.variant_group,
            name="Large",
            price_diff=500,
        )

        # ─────────────────────────────
        # Addon Group / Addon
        # ─────────────────────────────
        self.addon_group = MenuItemAddonGroup.objects.create(
            item=self.menu_item,
            name="Extras",
        )

        # FIXED: removed invalid "name" field
        self.addon = MenuItemAddon.objects.create(
            base_item=self.addon_base,
            price=200,
        )

        self.addon.groups.add(self.addon_group)

    # ================================================================
    # DELETE ADDON
    # ================================================================
    def test_delete_addon_success(self):
        url = reverse("delete-addon", kwargs={"addon_id": self.addon.id})

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(MenuItemAddon.objects.filter(id=self.addon.id).exists())

        self.assertFalse(BaseItem.objects.filter(id=self.addon_base.id).exists())

        self.assertFalse(
            BaseItemAvailability.objects.filter(base_item=self.addon_base).exists()
        )

        self.assertTrue(response.data["base_item_deleted"])

    # ================================================================
    def test_delete_addon_not_found(self):
        url = reverse("delete-addon", kwargs={"addon_id": 999999999})

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["detail"], "Addon not found.")

    # ================================================================
    # DELETE MENU ITEM
    # ================================================================
    def test_delete_menu_item_success(self):
        url = reverse("delete-menu-item", kwargs={"item_id": self.menu_item.id})

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(MenuItem.objects.filter(id=self.menu_item.id).exists())
        self.assertFalse(VariantGroup.objects.filter(id=self.variant_group.id).exists())
        self.assertFalse(VariantOption.objects.filter(id=self.variant_option.id).exists())
        self.assertFalse(MenuItemAddonGroup.objects.filter(id=self.addon_group.id).exists())
        self.assertFalse(MenuItemAddon.objects.filter(id=self.addon.id).exists())

    # ================================================================
    # DELETE CATEGORY
    # ================================================================
    def test_delete_category_success(self):
        url = reverse("delete-category", kwargs={"category_id": self.category.id})

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(MenuCategory.objects.filter(id=self.category.id).exists())
        self.assertFalse(MenuItem.objects.filter(id=self.menu_item.id).exists())

    # ================================================================
    # DELETE MENU
    # ================================================================
    def test_delete_menu_success(self):
        url = reverse("delete-menu", kwargs={"menu_id": self.menu.id})

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(Menu.objects.filter(id=self.menu.id).exists())
        self.assertFalse(MenuCategory.objects.filter(id=self.category.id).exists())
        self.assertFalse(MenuItem.objects.filter(id=self.menu_item.id).exists())

    # ================================================================
    # BULK DELETE
    # ================================================================
    def test_bulk_delete_success(self):
        menu_2 = Menu.objects.create(
            business=self.business,
            name="Second Menu",
        )

        category_2 = MenuCategory.objects.create(
            menu=menu_2,
            name="Pizza",
        )

        base_2 = BaseItem.objects.create(
            business=self.business,
            name="Pizza Base",
            default_price=100
        )

        MenuItem.objects.create(
            category=category_2,
            base_item=base_2,
            custom_name="Pepperoni Pizza",
            price=1200
        )

        url = reverse("bulk-delete-menu")

        payload = {
            "menus": [str(menu_2.id)],
            "categories": [str(self.category.id)],
            "items": [],
            "addons": [],
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(Menu.objects.filter(id=menu_2.id).exists())
        self.assertFalse(MenuCategory.objects.filter(id=self.category.id).exists())

    # ================================================================
    def test_bulk_delete_no_ids(self):
        url = reverse("bulk-delete-menu")

        response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["non_field_errors"][0],
            "At least one ID must be provided across menus, categories, items, or addons."
        )
