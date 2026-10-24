import pytest
from rest_framework.test import APIClient
from decimal import Decimal

from accounts.models import User, DriverProfile, Business, Branch
from admin_api.models import AppAdmin
from payments.models import PlatformConfig


@pytest.fixture
def admin_client():
    client = APIClient()
    user = User.objects.create_user(
        email="superadmin@example.com",
        phone_number="+2348099999999",
        password="securepass123",
        is_staff=True,
    )
    AppAdmin.objects.create(user=user, name="SuperAdmin", role=AppAdmin.Role.ADMIN)

    login_resp = client.post(
        "/api/admin/login/",
        {"phone_number": "+2348099999999", "password": "securepass123"},
        format="json",
    )
    token = login_resp.data.get("access")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client, user


@pytest.mark.django_db
def test_import_integrity():
    from admin_api import views
    from admin_api.views import (
        BaseAppAdminAPIView,
        AdminDashboardStatsView,
        AdminUserStatusView,
        AdminSystemSettingsView,
    )
    assert hasattr(views, "BaseAppAdminAPIView")
    assert hasattr(views, "AdminDashboardStatsView")
    assert hasattr(views, "AdminFinanceDashboardView")
    assert hasattr(views, "AdminUserStatusView")
    assert hasattr(views, "AdminDriverStatusView")
    assert hasattr(views, "AdminBusinessStatusView")
    assert hasattr(views, "AdminSystemSettingsView")


@pytest.mark.django_db
def test_admin_dashboard_stats(admin_client):
    client, _ = admin_client
    resp = client.get("/api/admin/dashboard/stats/")
    assert resp.status_code == 200
    assert "users" in resp.data
    assert "realtime" in resp.data
    assert "today" in resp.data
    assert "withdrawals" in resp.data
    assert "active_riders" in resp.data["realtime"]
    assert "online_restaurants" in resp.data["realtime"]


@pytest.mark.django_db
def test_admin_finance_dashboard(admin_client):
    client, _ = admin_client
    resp = client.get("/api/admin/finance/dashboard/")
    assert resp.status_code == 200
    assert "revenue" in resp.data
    assert "payouts" in resp.data
    assert "platform_earnings" in resp.data


@pytest.mark.django_db
def test_admin_user_status_and_password_reset(admin_client):
    client, _ = admin_client
    customer = User.objects.create_user(
        email="customer1@example.com",
        phone_number="+2348011112222",
        password="oldpassword",
    )

    # Suspend user
    resp = client.patch(
        f"/api/admin/users/{customer.id}/status/",
        {"is_active": False, "reason": "Suspicious behavior"},
        format="json",
    )
    assert resp.status_code == 200
    customer.refresh_from_db()
    assert customer.is_active is False

    # Password reset
    resp = client.post(
        f"/api/admin/users/{customer.id}/reset-password/",
        {"new_password": "NewSecretPassword123!"},
        format="json",
    )
    assert resp.status_code == 200
    customer.refresh_from_db()
    assert customer.check_password("NewSecretPassword123!")


@pytest.mark.django_db
def test_admin_customer_wallet_credit(admin_client):
    client, _ = admin_client
    customer = User.objects.create_user(
        email="wallet_cust@example.com",
        phone_number="+2348033334444",
        password="custpass123",
    )

    resp = client.post(
        f"/api/admin/users/{customer.id}/credit-wallet/",
        {"amount_ngn": "1500.00", "reason": "App compensation"},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["amount_ngn"] == Decimal("1500.00")
    assert resp.data["balance_after_ngn"] == Decimal("1500.00")


@pytest.mark.django_db
def test_admin_business_status_and_commission(admin_client):
    client, _ = admin_client
    business = Business.objects.create(
        business_name="Test Kitchen",
        onboarding_complete=False,
    )

    # Approve business
    resp = client.post(
        f"/api/admin/employees/businesses/{business.id}/status/",
        {"action": "approve"},
        format="json",
    )
    assert resp.status_code == 200
    business.refresh_from_db()
    assert business.onboarding_complete is True

    # Custom commission
    resp = client.post(
        f"/api/admin/employees/businesses/{business.id}/commission/",
        {"commission_rate": "12.50"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["commission_rate"] == Decimal("12.50")

    get_resp = client.get(f"/api/admin/employees/businesses/{business.id}/commission/")
    assert get_resp.status_code == 200
    assert get_resp.data["commission_rate"] == Decimal("12.50")
    assert get_resp.data["is_custom"] is True


@pytest.mark.django_db
def test_admin_system_settings_no_holiday_mode(admin_client):
    client, _ = admin_client
    # GET settings
    get_resp = client.get("/api/admin/settings/")
    assert get_resp.status_code == 200
    assert "holiday_mode" not in get_resp.data  # specifically excluded
    assert "service_fee_percent" in get_resp.data
    assert "delivery_base_fee_ngn" in get_resp.data

    # PATCH settings
    patch_resp = client.patch(
        "/api/admin/settings/",
        {
            "service_fee_percent": 5.0,
            "delivery_base_fee_ngn": "750.00",
            "maintenance_mode": True,
        },
        format="json",
    )
    assert patch_resp.status_code == 200
    assert patch_resp.data["updated"]["service_fee_percent"] == 5.0

    # Verify updated values
    check_resp = client.get("/api/admin/settings/")
    assert check_resp.data["service_fee_percent"] == 5.0
    assert check_resp.data["delivery_base_fee_ngn"] == Decimal("750.00")
    assert check_resp.data["maintenance_mode"] is True
