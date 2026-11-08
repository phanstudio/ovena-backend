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


@pytest.mark.django_db
def test_admin_send_bulk_notifications_combinations_and_push(admin_client, monkeypatch):
    from accounts.models import CustomerProfile, BusinessAdmin, PrimaryAgent
    from notifications.models import Notification

    client, admin_user = admin_client

    push_calls = []

    def fake_send_push_to_users(users, title, body, data=None):
        push_calls.append(("bulk", [u.id for u in users], title, body, data))

    def fake_send_push_to_user(user, title, body, data=None):
        push_calls.append(("single", user.id, title, body, data))

    monkeypatch.setattr("notifications.services.send_push_to_users", fake_send_push_to_users)
    monkeypatch.setattr("notifications.services.send_push_to_user", fake_send_push_to_user)

    # 1. Customer user
    cust_user = User.objects.create_user(email="cust@example.com", phone_number="+2348010000001")
    CustomerProfile.objects.create(user=cust_user, name="Customer One")

    # 2. Driver user (who is ALSO a customer — tests deduplication!)
    driver_user = User.objects.create_user(email="driver@example.com", phone_number="+2348010000002")
    DriverProfile.objects.create(user=driver_user, first_name="Driver", last_name="One")
    CustomerProfile.objects.create(user=driver_user, name="Driver Customer")

    # 3. Business Admin user
    badmin_user = User.objects.create_user(email="badmin@example.com", phone_number="+2348010000003")
    biz = Business.objects.create(business_name="Oven Hub")
    badmin = BusinessAdmin.objects.create(user=badmin_user, business=biz, name="Biz Owner")

    # 4. Active Business Staff (PrimaryAgent)
    bstaff_user = User.objects.create_user(email="bstaff@example.com", phone_number="+2348010000004")
    branch1 = Branch.objects.create(business=biz, name="Main Branch")
    PrimaryAgent.objects.create(
        branch=branch1,
        user=bstaff_user,
        created_by=badmin,
        device_name="POS-1",
        revoked=False,
    )

    # 5. Revoked Business Staff (should NOT receive business notifications)
    revoked_staff_user = User.objects.create_user(email="revoked@example.com", phone_number="+2348010000005")
    branch2 = Branch.objects.create(business=biz, name="Second Branch")
    PrimaryAgent.objects.create(
        branch=branch2,
        user=revoked_staff_user,
        created_by=badmin,
        device_name="POS-2",
        revoked=True,
    )

    # Case A: Combination of "customers" and "businesses"
    # Should notify: cust_user, driver_user (has customer profile), badmin_user, bstaff_user (4 distinct users)
    resp = client.post(
        "/api/admin/notifications/send/",
        {
            "audiences": ["customers", "businesses"],
            "title": "Promo Update",
            "body": "Big news for customers and businesses!",
        },
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["created"] == 4
    assert resp.data["audiences"] == ["customers", "businesses"]
    assert len(push_calls) == 1
    assert set(push_calls[0][1]) == {cust_user.id, driver_user.id, badmin_user.id, bstaff_user.id}
    assert revoked_staff_user.id not in push_calls[0][1]

    # Case B: Deduplication when user matches multiple selected audiences ("customers" + "drivers")
    Notification.objects.all().delete()
    push_calls.clear()
    resp = client.post(
        "/api/admin/notifications/send/",
        {
            "audiences": ["customers", "drivers"],
            "title": "Customer + Driver Notice",
            "body": "Deduplicated message",
        },
        format="json",
    )
    assert resp.status_code == 200
    # Only cust_user and driver_user (2 distinct users, even though driver_user is in both)
    assert resp.data["created"] == 2
    assert Notification.objects.filter(user=driver_user).count() == 1

    # Case C: Separate "business_admins" vs "business_staff" vs "admins"
    Notification.objects.all().delete()
    push_calls.clear()
    resp = client.post(
        "/api/admin/notifications/send/",
        {
            "audiences": ["business_staff", "admins"],
            "title": "Staff & Admin Alert",
            "body": "Internal notice",
            "push": False,
        },
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["created"] == 2  # bstaff_user + admin_user
    assert len(push_calls) == 0  # push=False skipped FCM

    # Case D: Single user_id with push=True
    resp = client.post(
        "/api/admin/notifications/send/",
        {
            "user_id": cust_user.id,
            "title": "Direct Message",
            "body": "Hello Customer",
        },
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["detail"] == "Notification sent"
    assert len(push_calls) == 1
    assert push_calls[0][0] == "single"
    assert push_calls[0][1] == cust_user.id

