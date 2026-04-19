import pytest

from rest_framework.test import APIClient

from accounts.models import User
from admin_api.models import AppAdmin


@pytest.mark.django_db
def test_app_admin_can_login_and_access_dashboard():
    client = APIClient()

    user = User.objects.create_user(
        email="admin@example.com",
        phone_number="+2348012345678",
        password="pass1234",
        name="Admin",
        is_staff=True,
    )
    AppAdmin.objects.create(user=user, name="Admin", role=AppAdmin.Role.ADMIN)

    resp = client.post(
        "/api/admin/login/",
        {"phone_number": "+2348012345678", "password": "pass1234"},
        format="json",
    )
    assert resp.status_code == 200
    access = resp.data.get("access")
    assert access

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    stats = client.get("/api/admin/dashboard/stats/")
    assert stats.status_code == 200
    assert "users" in stats.data
    assert "withdrawals" in stats.data

