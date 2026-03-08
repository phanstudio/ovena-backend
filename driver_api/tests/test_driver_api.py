import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import DriverBankAccount, DriverProfile, User
from driver_api.models import DriverLedgerEntry


def auth_header_for(user):
    token = RefreshToken.for_user(user).access_token
    return {"HTTP_AUTHORIZATION": f"Bearer {str(token)}"}


@pytest.mark.django_db
def test_non_driver_cannot_access_dashboard(client):
    user = User.objects.create(email="nondriver@example.com", name="No Driver")
    response = client.get("/api/driver/dashboard/", **auth_header_for(user))
    assert response.status_code == 403


@pytest.mark.django_db
def test_driver_profile_endpoint(client):
    user = User.objects.create(email="driver1@example.com", name="Driver One")
    profile = DriverProfile.objects.create(user=user, first_name="Driver", last_name="One")
    response = client.get("/api/driver/profile/", **auth_header_for(user))
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["first_name"] == profile.first_name


@pytest.mark.django_db
def test_withdrawal_idempotency_key_returns_existing_record(client):
    user = User.objects.create(email="driver2@example.com", name="Driver Two")
    profile = DriverProfile.objects.create(user=user, first_name="Driver", last_name="Two")
    DriverBankAccount.objects.create(
        driver=profile,
        bank_code="058",
        bank_name="GTBank",
        account_number="0123456789",
        account_name="Driver Two",
        is_verified=True,
    )
    DriverLedgerEntry.objects.create(
        driver=profile,
        entry_type=DriverLedgerEntry.TYPE_CREDIT,
        amount="5000.00",
        source_type="seed",
        source_id="1",
        status=DriverLedgerEntry.STATUS_POSTED,
    )
    headers = {
        **auth_header_for(user),
        "HTTP_IDEMPOTENCY_KEY": "idem-123",
    }
    first = client.post("/api/driver/withdrawals/", data='{"amount":"100.00"}', content_type="application/json", **headers)
    second = client.post("/api/driver/withdrawals/", data='{"amount":"100.00"}', content_type="application/json", **headers)

    assert first.status_code == 201
    assert second.status_code == 200
    first_id = first.json()["data"]["id"]
    second_id = second.json()["data"]["id"]
    assert first_id == second_id
