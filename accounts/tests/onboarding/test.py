"""
Comprehensive pytest test suite for the Business Onboarding Flow.
Covers: RegisterBAdmin, Phase1, Phase2, Phase3 (RegisterMenus)

Setup assumptions:
    - pytest-django installed
    - conftest.py sets up Django settings
    - Models: User, Business, BusinessAdmin, BusinessCerd, Branch,
              BranchOperatingHours, BusinessPayoutAccount,
              BaseItem, BaseItemAvailability,
              Menu, MenuCategory, MenuItem,
              VariantGroup, VariantOption,
              MenuItemAddonGroup, MenuItemAddon

Run with:
    pytest tests/test_onboarding.py -v
"""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

User = get_user_model()


# ===========================================================================
# FIXTURES
# ===========================================================================

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(api_client, business_admin_user, access_token):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    return api_client


@pytest.fixture
def business_admin_user(db):
    return User.objects.create(
        name="Chidi Okeke",
        phone_number="+2348012345678",
        role="businessadmin",
    )


@pytest.fixture
def access_token(business_admin_user):
    from authflow.services import issue_jwt_for_user  # adjust import
    tokens = issue_jwt_for_user(business_admin_user)
    return tokens["access"]


@pytest.fixture
def business(db, business_admin_user):
    from accounts.models import Business, BusinessAdmin, BusinessCerd
    biz = Business.objects.create(
        business_name="Chidi's Kitchen",
        business_type="restaurant",
        country="NG",
        business_address="12 Broad Street, Lagos",
        email="chidi@kitchen.com",
        phone_number="+2348012345678",
    )
    BusinessCerd.objects.create(business=biz)
    BusinessAdmin.objects.create(business=biz, user=business_admin_user)
    return biz


@pytest.fixture
def branch(db, business):
    from accounts.models import Branch
    return Branch.objects.create(
        business=business,
        name="Lekki Branch",
        address="5 Admiralty Way, Lekki",
        delivery_method="instant",
    )


@pytest.fixture
def valid_phase2_payload():
    return {
        "registered_business_name": "Chidi's Kitchen Ltd",
        "business_type": "LLC",
        "tax_identification_number": "TIN-00123456",
        "rc_number": "RC-987654",
        "payment": {
            "bank": "Access Bank",
            "account_number": "0123456789",
            "account_name": "Chidi Okeke",
            "bvn": "22198765432",
        },
        "branches": [
            {
                "name": "Lekki Branch",
                "address": "5 Admiralty Way, Lekki Phase 1",
                "longitude": 3.677,
                "latitude": 4.564,
                "delivery_method": "instant",
                "operating_hours": [
                    {"day": 0, "open_time": "08:00", "close_time": "22:00", "is_closed": False},
                    {"day": 6, "open_time": "00:00", "close_time": "00:00", "is_closed": True},
                ],
            }
        ],
    }


@pytest.fixture
def valid_menu_payload():
    return {
        "menus": [
            {
                "name": "Main Menu",
                "description": "Everyday menu",
                "is_active": True,
                "categories": [
                    {
                        "name": "Burgers",
                        "sort_order": 1,
                        "items": [
                            {
                                "custom_name": "Classic Cheeseburger",
                                "price": "3500.00",
                                "base_item": {
                                    "name": "Cheeseburger",
                                    "description": "Beef patty with cheddar",
                                    "price": "3500.00",
                                },
                                "variant_groups": [
                                    {
                                        "name": "Patty Size",
                                        "is_required": True,
                                        "options": [
                                            {"name": "Single", "price_diff": "0.00"},
                                            {"name": "Double", "price_diff": "800.00"},
                                        ],
                                    }
                                ],
                                "addon_groups": [
                                    {
                                        "name": "Extra Toppings",
                                        "is_required": False,
                                        "max_selection": 3,
                                        "addons": [
                                            {
                                                "price": "300.00",
                                                "base_item": {"name": "Cheese Slice", "price": "300.00"},
                                            },
                                            {
                                                "price": "400.00",
                                                "base_item": {"name": "Bacon Strip", "price": "400.00"},
                                            },
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


# ===========================================================================
# STEP 1: RegisterBAdmin
# ===========================================================================

# class TestRegisterBAdmin:

#     @patch("authflow.services.verify")
#     def test_register_success(self, mock_verify, db, api_client):
#         mock_verify.return_value = "+2348012345678"
#         response = api_client.post(reverse("register-businessadmin"), {
#             "full_name": "Chidi Okeke",
#             "phone_number": "+2348012345678",
#             "otp_code": "123456",
#         })
#         assert response.status_code == 201
#         assert "access" in response.data
#         assert "refresh" in response.data
#         assert response.data["user"]["name"] == "Chidi Okeke"
#         assert User.objects.filter(phone_number="+2348012345678").exists()

#     def test_missing_fields_returns_400(self, db, api_client):
#         response = api_client.post(reverse("register-businessadmin"), {
#             "phone_number": "+2348012345678",
#             "otp_code": "123456",
#             # missing full_name
#         })
#         assert response.status_code == 400

#     @patch("authflow.services.verify")
#     def test_invalid_otp_returns_400(self, mock_verify, db, api_client):
#         from authflow.services import OTPInvalidError
#         mock_verify.side_effect = OTPInvalidError("Invalid OTP")
#         response = api_client.post(reverse("register-businessadmin"), {
#             "full_name": "Chidi Okeke",
#             "phone_number": "+2348012345678",
#             "otp_code": "000000",
#         })
#         assert response.status_code == 400
#         assert "error" in response.data

#     @patch("authflow.services.verify")
#     def test_duplicate_phone_returns_400(self, mock_verify, db, api_client, business_admin_user):
#         mock_verify.return_value = business_admin_user.phone_number
#         response = api_client.post(reverse("register-businessadmin"), {
#             "full_name": "Another Person",
#             "phone_number": business_admin_user.phone_number,
#             "otp_code": "123456",
#         })
#         # print(response.data)
#         assert response.status_code == 400
#         assert "already taken" in response.data["error"].lower()

#     @patch("authflow.services.verify")
#     def test_jwt_tokens_are_valid(self, mock_verify, db, api_client):
#         mock_verify.return_value = "+2348099999999"
#         response = api_client.post(reverse("register-businessadmin"), {
#             "full_name": "Test User",
#             "phone_number": "+2348099999999",
#             "otp_code": "111111",
#         })
#         assert response.status_code == 201
#         assert len(response.data["access"]) > 20
#         assert len(response.data["refresh"]) > 20


# # ===========================================================================
# # STEP 2: Phase 1 — Business Registration
# # ===========================================================================

# class TestPhase1Registration:

#     def test_phase1_success(self, db, auth_client, business_admin_user):
#         response = auth_client.post(reverse("register-phase1"), {
#             "business_name": "Chidi's Kitchen",
#             "business_type": "restaurant",
#             "country": "Nigeria",
#             "business_address": "12 Broad Street, Lagos",
#             "email": "chidi@kitchen.com",
#             "phone_number": "+2348012345678",
#             "password": "SecurePass123!",
#         })
#         assert response.status_code == 201
#         assert "business_id" in response.data

#     def test_incorrect_contrycode(self, db, auth_client, business_admin_user):
#         response = auth_client.post(reverse("register-phase1"), {
#             "business_name": "Chidi's Kitchen",
#             "business_type": "restaurant",
#             "country": "zz",
#             "business_address": "12 Broad Street, Lagos",
#             "email": "chidi@kitchen.com",
#             "phone_number": "+2348012345678",
#             "password": "SecurePass123!",
#         })
#         assert response.status_code == 400

#     def test_correct_country_code(self, db, auth_client, business_admin_user):
#         response = auth_client.post(reverse("register-phase1"), {
#             "business_name": "Chidi's Kitchen",
#             "business_type": "restaurant",
#             "country": "NG",
#             "business_address": "12 Broad Street, Lagos",
#             "email": "chidi@kitchen.com",
#             "phone_number": "+2348012345678",
#             "password": "SecurePass123!",
#         })
#         assert response.status_code == 201
#         assert "business_id" in response.data

#     def test_phase1_creates_business_admin_link(self, db, auth_client, business_admin_user):
#         from accounts.models import BusinessAdmin
#         auth_client.post(reverse("register-phase1"), {
#             "business_name": "Test Biz",
#             "business_type": "restaurant",
#             "country": "Nigeria",
#             "business_address": "1 Test St",
#             "email": "test@biz.com",
#             "phone_number": "+2348011111111",
#             "password": "Pass1234!",
#         })
#         assert BusinessAdmin.objects.filter(user=business_admin_user).exists()

#     def test_phase1_creates_business_cerd(self, db, auth_client, business_admin_user):
#         from accounts.models import Business, BusinessCerd
#         response = auth_client.post(reverse("register-phase1"), {
#             "business_name": "Cerd Test Kitchen",
#             "business_type": "restaurant",
#             "country": "Nigeria",
#             "business_address": "2 Test St",
#             "email": "cerd@test.com",
#             "phone_number": "+2348022222222",
#             "password": "Pass1234!",
#         })
#         biz = Business.objects.get(id=response.data["business_id"])
#         assert BusinessCerd.objects.filter(business=biz).exists()

#     def test_phase1_missing_fields_returns_400(self, db, auth_client):
#         response = auth_client.post(reverse("register-phase1"), {
#             "business_name": "Incomplete Biz",
#             # missing everything else
#         })
#         assert response.status_code == 400

#     def test_phase1_requires_authentication(self, db, api_client):
#         response = api_client.post(reverse("register-phase1"), {
#             "business_name": "Unauthed Biz",
#         })
#         assert response.status_code in (401, 403)

#     def test_phase1_sets_password_on_user(self, db, auth_client, business_admin_user):
#         auth_client.post(reverse("register-phase1"), {
#             "business_name": "Password Test",
#             "business_type": "restaurant",
#             "country": "Nigeria",
#             "business_address": "3 Test St",
#             "email": "pw@test.com",
#             "phone_number": "+2348033333333",
#             "password": "MyNewPass999!",
#         })
#         business_admin_user.refresh_from_db()
#         assert business_admin_user.check_password("MyNewPass999!")


# # ===========================================================================
# # STEP 3: Phase 2 — Onboarding
# # ===========================================================================

# class TestPhase2Onboarding:

#     def test_phase2_success(self, db, auth_client, business, valid_phase2_payload):
#         response = auth_client.post(reverse("register-phase2"), valid_phase2_payload, format="json")
#         assert response.status_code == 200
#         assert response.data["detail"] == "Onboarding complete."

#     def test_phase2_creates_branch(self, db, auth_client, business, valid_phase2_payload):
#         from accounts.models import Branch
#         auth_client.post(reverse("register-phase2"), valid_phase2_payload, format="json")
#         assert Branch.objects.filter(business=business, name="Lekki Branch").exists()

#     def test_phase2_creates_operating_hours(self, db, auth_client, business, valid_phase2_payload):
#         from accounts.models import Branch, BranchOperatingHours
#         auth_client.post(reverse("register-phase2"), valid_phase2_payload, format="json")
#         branch = Branch.objects.get(business=business, name="Lekki Branch")
#         hours = BranchOperatingHours.objects.filter(branch=branch)
#         assert hours.count() == 2
#         monday = hours.get(day=0)
#         assert str(monday.open_time) == "08:00:00"
#         assert str(monday.close_time) == "22:00:00"
#         sunday = hours.get(day=6)
#         assert sunday.is_closed is True

#     def test_phase2_creates_payment_account(self, db, auth_client, business, valid_phase2_payload):
#         from accounts.models import BusinessPayoutAccount
#         auth_client.post(reverse("register-phase2"), valid_phase2_payload, format="json")
#         account = BusinessPayoutAccount.objects.get(business=business)
#         assert account.bank_name == "Access Bank"
#         assert account.account_number == "0123456789"

#     def test_phase2_payment_upsert(self, db, auth_client, business, valid_phase2_payload):
#         """Calling phase2 twice should update, not duplicate, the payment record."""
#         from accounts.models import BusinessPayoutAccount
#         auth_client.post(reverse("register-phase2"), valid_phase2_payload, format="json")
#         valid_phase2_payload["payment"]["bank"] = "GTBank"
#         auth_client.post(reverse("register-phase2"), valid_phase2_payload, format="json")
#         assert BusinessPayoutAccount.objects.filter(business=business).count() == 1
#         assert BusinessPayoutAccount.objects.get(business=business).bank_name == "GTBank"

#     def test_phase2_sets_onboarding_complete(self, db, auth_client, business, valid_phase2_payload):
#         auth_client.post(reverse("register-phase2"), valid_phase2_payload, format="json")
#         business.refresh_from_db()
#         assert business.onboarding_complete is True

#     def test_phase2_multiple_branches(self, db, auth_client, business):
#         from accounts.models import Branch
#         payload = {
#             "registered_business_name": "Multi Branch Biz",
#             "branches": [
#                 {"name": "Branch A", "delivery_method": "instant", "operating_hours": []},
#                 {"name": "Branch B", "delivery_method": "scheduled",
#                  "pre_order_open_period": "09:00", "final_order_time": "21:00", "operating_hours": []},
#             ],
#         }
#         response = auth_client.post(reverse("register-phase2"), payload, format="json")
#         assert response.status_code == 200
#         assert Branch.objects.filter(business=business).count() == 2

#     def test_phase2_no_auth_returns_403(self, db, api_client, business):
#         response = api_client.post(reverse("register-phase2"), {}, format="json")
#         assert response.status_code in (401, 403)

#     def test_phase2_user_without_business_returns_403(self, db, api_client):
#         """User who skipped phase1 should be rejected."""
#         from accounts.models import User
#         from authflow.services import issue_jwt_for_user
#         orphan_user = User.objects.create(name="Orphan", phone_number="+2340000000001", role="businessadmin")
#         tokens = issue_jwt_for_user(orphan_user)
#         api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
#         response = api_client.post(reverse("register-phase2"), {"registered_business_name": "X"}, format="json")
#         assert response.status_code == 403


# # ===========================================================================
# # STEP 4: Phase 3 — Menu Registration
# # ===========================================================================

# class TestPhase3MenuRegistration:

#     def test_phase3_success(self, db, auth_client, business, branch, valid_menu_payload):
#         response = auth_client.post(reverse("register-menus-ob"), valid_menu_payload, format="json")
#         assert response.status_code == 201
#         assert response.data["message"] == "Menus registered successfully"

#     def test_phase3_creates_menu(self, db, auth_client, business, branch, valid_menu_payload):
#         from menu.models import Menu
#         auth_client.post(reverse("register-menus-ob"), valid_menu_payload, format="json")
#         assert Menu.objects.filter(business=business, name="Main Menu").exists()

#     def test_phase3_creates_category(self, db, auth_client, business, branch, valid_menu_payload):
#         from menu.models import MenuCategory
#         auth_client.post(reverse("register-menus-ob"), valid_menu_payload, format="json")
#         assert MenuCategory.objects.filter(name="Burgers").exists()

#     def test_phase3_creates_menu_item(self, db, auth_client, business, branch, valid_menu_payload):
#         from menu.models import MenuItem
#         auth_client.post(reverse("register-menus-ob"), valid_menu_payload, format="json")
#         item = MenuItem.objects.get(custom_name="Classic Cheeseburger")
#         assert item.price == Decimal("3500.00")

#     def test_phase3_creates_base_item(self, db, auth_client, business, branch, valid_menu_payload):
#         from menu.models import BaseItem
#         auth_client.post(reverse("register-menus-ob"), valid_menu_payload, format="json")
#         assert BaseItem.objects.filter(business=business, name="Cheeseburger").exists()
#         assert BaseItem.objects.filter(business=business, name="Cheese Slice").exists()
#         assert BaseItem.objects.filter(business=business, name="Bacon Strip").exists()

#     def test_phase3_base_items_not_duplicated_on_resubmit(self, db, auth_client, business, branch, valid_menu_payload):
#         """Submitting the same base item name twice should not create duplicates."""
#         from menu.models import BaseItem
#         auth_client.post(reverse("register-menus-ob"), valid_menu_payload, format="json")
#         auth_client.post(reverse("register-menus-ob"), valid_menu_payload, format="json")
#         assert BaseItem.objects.filter(business=business, name="Cheeseburger").count() == 1

#     def test_phase3_creates_variant_groups_and_options(self, db, auth_client, business, branch, valid_menu_payload):
#         from menu.models import VariantGroup, VariantOption
#         auth_client.post(reverse("register-menus-ob"), valid_menu_payload, format="json")
#         group = VariantGroup.objects.get(name="Patty Size")
#         assert group.is_required is True
#         options = VariantOption.objects.filter(group=group)
#         assert options.count() == 2
#         assert options.filter(name="Double", price_diff=Decimal("800.00")).exists()

#     def test_phase3_creates_addon_groups(self, db, auth_client, business, branch, valid_menu_payload):
#         from menu.models import MenuItemAddonGroup
#         auth_client.post(reverse("register-menus-ob"), valid_menu_payload, format="json")
#         group = MenuItemAddonGroup.objects.get(name="Extra Toppings")
#         assert group.is_required is False
#         assert group.max_selection == 3

#     def test_phase3_creates_addons_with_m2m_links(self, db, auth_client, business, branch, valid_menu_payload):
#         from menu.models import MenuItemAddon, MenuItemAddonGroup
#         auth_client.post(reverse("register-menus-ob"), valid_menu_payload, format="json")
#         group = MenuItemAddonGroup.objects.get(name="Extra Toppings")
#         addons = MenuItemAddon.objects.filter(groups=group)
#         assert addons.count() == 2
#         assert addons.filter(base_item__name="Cheese Slice").exists()
#         assert addons.filter(base_item__name="Bacon Strip").exists()

#     def test_phase3_bootstraps_availability_for_all_branches(self, db, auth_client, business, branch, valid_menu_payload):
#         from menu.models import BaseItemAvailability
#         # Add a second branch to confirm all branches get covered
#         from accounts.models import Branch
#         branch2 = Branch.objects.create(business=business, name="VI Branch", delivery_method="instant")

#         auth_client.post(reverse("register-menus-ob"), valid_menu_payload, format="json")

#         for br in [branch, branch2]:
#             for name in ["Cheeseburger", "Cheese Slice", "Bacon Strip"]:
#                 assert BaseItemAvailability.objects.filter(
#                     branch=br, base_item__name=name
#                 ).exists(), f"Missing availability for {name} at {br.name}"

#     def test_phase3_availability_not_duplicated(self, db, auth_client, business, branch, valid_menu_payload):
#         """Resubmitting should not create duplicate availability rows."""
#         from menu.models import BaseItemAvailability
#         auth_client.post(reverse("register-menus-ob"), valid_menu_payload, format="json")
#         auth_client.post(reverse("register-menus-ob"), valid_menu_payload, format="json")
#         assert BaseItemAvailability.objects.filter(
#             branch=branch, base_item__name="Cheeseburger"
#         ).count() == 1

#     def test_phase3_empty_menus_returns_400(self, db, auth_client, business, branch):
#         response = auth_client.post(reverse("register-menus-ob"), {"menus": []}, format="json")
#         assert response.status_code == 400

#     def test_phase3_no_base_items_returns_400(self, db, auth_client, business, branch):
#         """A menu payload that somehow resolves to no base items should be rejected."""
#         bad_payload = {
#             "menus": [
#                 {
#                     "name": "Empty Menu",
#                     "categories": [
#                         {"name": "Empty Cat", "sort_order": 0, "items": []}
#                     ],
#                 }
#             ]
#         }
#         response = auth_client.post(reverse("register-menus-ob"), bad_payload, format="json")
#         assert response.status_code == 400

#     def test_phase3_response_contains_correct_base_item_count(self, db, auth_client, business, branch, valid_menu_payload):
#         response = auth_client.post(reverse("register-menus-ob"), valid_menu_payload, format="json")
#         # Cheeseburger, Cheese Slice, Bacon Strip = 3 unique base items
#         assert response.data["base_items_referenced"] == 3

#     def test_phase3_shared_base_item_across_addons_and_items(self, db, auth_client, business, branch):
#         """
#         Bacon Strip appears in both a menu item and an addon.
#         Should create only one BaseItem.
#         """
#         from menu.models import BaseItem
#         payload = {
#             "menus": [
#                 {
#                     "name": "Shared Base Test",
#                     "categories": [
#                         {
#                             "name": "Mains",
#                             "sort_order": 1,
#                             "items": [
#                                 {
#                                     "custom_name": "Bacon Plate",
#                                     "price": "2000.00",
#                                     "base_item": {"name": "Bacon Strip", "price": "2000.00"},
#                                     "addon_groups": [
#                                         {
#                                             "name": "Extras",
#                                             "is_required": False,
#                                             "max_selection": 1,
#                                             "addons": [
#                                                 {
#                                                     "price": "400.00",
#                                                     "base_item": {"name": "Bacon Strip", "price": "400.00"},
#                                                 }
#                                             ],
#                                         }
#                                     ],
#                                 }
#                             ],
#                         }
#                     ],
#                 }
#             ]
#         }
#         auth_client.post(reverse("register-menus-ob"), payload, format="json")
#         assert BaseItem.objects.filter(business=business, name="Bacon Strip").count() == 1

#     def test_phase3_multiple_menus(self, db, auth_client, business, branch):
#         from menu.models import Menu
#         payload = {
#             "menus": [
#                 {
#                     "name": "Breakfast Menu",
#                     "categories": [
#                         {
#                             "name": "Morning",
#                             "sort_order": 1,
#                             "items": [
#                                 {
#                                     "custom_name": "Eggs",
#                                     "price": "1500.00",
#                                     "base_item": {"name": "Scrambled Eggs", "price": "1500.00"},
#                                 }
#                             ],
#                         }
#                     ],
#                 },
#                 {
#                     "name": "Dinner Menu",
#                     "categories": [
#                         {
#                             "name": "Mains",
#                             "sort_order": 1,
#                             "items": [
#                                 {
#                                     "custom_name": "Jollof Rice",
#                                     "price": "2500.00",
#                                     "base_item": {"name": "Jollof Rice", "price": "2500.00"},
#                                 }
#                             ],
#                         }
#                     ],
#                 },
#             ]
#         }
#         response = auth_client.post(reverse("register-menus-ob"), payload, format="json")
#         assert response.status_code == 201
#         assert len(response.data["menus"]) == 2
#         assert Menu.objects.filter(business=business).count() == 2

#     def test_phase3_price_fallback_to_base_item_default(self, db, auth_client, business, branch):
#         """If MenuItem.price is not set, it should fall back to base_item.price."""
#         from menu.models import MenuItem
#         payload = {
#             "menus": [
#                 {
#                     "name": "Fallback Test",
#                     "categories": [
#                         {
#                             "name": "Cat",
#                             "sort_order": 0,
#                             "items": [
#                                 {
#                                     # no 'price' field set here
#                                     "base_item": {"name": "Mystery Dish", "price": "1800.00"},
#                                 }
#                             ],
#                         }
#                     ],
#                 }
#             ]
#         }
#         auth_client.post(reverse("register-menus-ob"), payload, format="json")
#         item = MenuItem.objects.get(base_item__name="Mystery Dish")
#         assert item.price == Decimal("1800.00")

#     def test_phase3_no_auth_returns_403(self, db, api_client, business):
#         response = api_client.post(reverse("register-menus-ob"), {}, format="json")
#         assert response.status_code in (401, 403)


# # ===========================================================================
# # BOOTSTRAP FUNCTION: Unit Tests
# # ===========================================================================

# class TestBootstrapBaseItemAvailability:

#     def test_creates_availability_for_all_branches_and_base_items(self, db, business, branch):
#         from menu.models import Branch, BaseItem, BaseItemAvailability
#         from menu.views import bootstrap_base_item_availability_for_business

#         branch2 = Branch.objects.create(business=business, name="Branch 2", delivery_method="instant")
#         bi1 = BaseItem.objects.create(business=business, name="Item A", default_price=100)
#         bi2 = BaseItem.objects.create(business=business, name="Item B", default_price=200)

#         base_by_name = {"Item A": bi1, "Item B": bi2}
#         base_ids = [b.id for b in base_by_name.values()]
#         count = bootstrap_base_item_availability_for_business(business, base_ids)

#         # 2 branches × 2 base items = 4 rows
#         assert count == 4
#         assert BaseItemAvailability.objects.filter(branch=branch).count() == 2
#         assert BaseItemAvailability.objects.filter(branch=branch2).count() == 2

#     def test_does_not_overwrite_existing_availability(self, db, business, branch):
#         from menu.models import BaseItem, BaseItemAvailability
#         from menu.views import bootstrap_base_item_availability_for_business

#         bi = BaseItem.objects.create(business=business, name="Toggle Item", default_price=100)
#         # Pre-existing row with is_available=False (operator toggled it off)
#         # BaseItemAvailability.objects.create(branch=branch, base_item=bi, is_available=False)
#         BaseItemAvailability.objects.update_or_create(
#             branch=branch,
#             base_item=bi,
#             defaults={"is_available": False},
#         )

#         bootstrap_base_item_availability_for_business(business, [bi.id])

#         # Should still be False — ignore_conflicts means don't overwrite
#         row = BaseItemAvailability.objects.get(branch=branch, base_item=bi)
#         assert row.is_available is False

#     def test_no_branches_returns_zero(self, db):
#         from menu.models import Business, BaseItem
#         from menu.views import bootstrap_base_item_availability_for_business

#         biz = Business.objects.create(
#             business_name="Empty Biz", business_type="restaurant",
#             country="NG", business_address="x", email="e@e.com", phone_number="+0"
#         )
#         bi = BaseItem.objects.create(business=biz, name="Lonely Item", default_price=100)
#         result = bootstrap_base_item_availability_for_business(biz, {"Lonely Item": bi})
#         assert result == 0

#     def test_no_base_items_returns_zero(self, db, business, branch):
#         from menu.views import bootstrap_base_item_availability_for_business
#         result = bootstrap_base_item_availability_for_business(business, {})
#         assert result == 0


# # ===========================================================================
# # INTEGRATION: Full Onboarding Flow End-to-End
# # ===========================================================================

class TestFullOnboardingFlow:

    @patch("authflow.services.verify")
    def test_complete_flow(self, mock_verify, db, api_client):
        from menu.models import (
            Business, Branch, MenuItem,
            BaseItem, BaseItemAvailability
        )

        # 1. Register admin
        mock_verify.return_value = "+2348099887766"
        r1 = api_client.post(reverse("register-businessadmin"), {
            "full_name": "Flow Tester",
            "phone_number": "+2348099887766",
            "otp_code": "999999",
        })
        assert r1.status_code == 201
        token = r1.data["access"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # 2. Phase 1 — create business
        r2 = api_client.post(reverse("register-phase1"), {
            "business_name": "Flow Kitchen",
            "business_type": "restaurant",
            "country": "Nigeria",
            "business_address": "1 Flow St",
            "email": "flow@kitchen.com",
            "phone_number": "+2348099887766",
            "password": "FlowPass123!",
        })
        assert r2.status_code == 201
        biz_id = r2.data["business_id"]

        # 3. Phase 2 — onboarding with 1 branch
        r3 = api_client.post(reverse("register-phase2"), {
            "registered_business_name": "Flow Kitchen Ltd",
            "branches": [
                {
                    "name": "Main Branch",
                    "address": "1 Flow St",
                    "longitude": 3.89,
                    "latitude": 6.7,
                    "delivery_method": "instant",
                    "operating_hours": [
                        {"day": 1, "open_time": "09:00", "close_time": "21:00", "is_closed": False},
                    ],
                }
            ],
        }, format="json")
        assert r3.status_code == 200

        # 4. Phase 3 — register menus
        r4 = api_client.post(reverse("register-menus-ob"), {
            "menus": [
                {
                    "name": "Flow Menu",
                    "categories": [
                        {
                            "name": "Mains",
                            "sort_order": 1,
                            "items": [
                                {
                                    "custom_name": "Puff Puff",
                                    "price": "500.00",
                                    "base_item": {"name": "Puff Puff", "price": "500.00"},
                                }
                            ],
                        }
                    ],
                }
            ]
        }, format="json")
        assert r4.status_code == 201

        # Final assertions
        biz = Business.objects.get(id=biz_id)
        branch = Branch.objects.get(business=biz, name="Main Branch")
        assert MenuItem.objects.filter(custom_name="Puff Puff").exists()
        assert BaseItem.objects.filter(business=biz, name="Puff Puff").exists()
        assert BaseItemAvailability.objects.filter(branch=branch, base_item__name="Puff Puff").exists()
        assert biz.onboarding_complete is True
