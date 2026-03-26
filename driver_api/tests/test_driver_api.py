from decimal import Decimal
from types import SimpleNamespace

import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import DriverBankAccount, DriverProfile, User
from driver_api.models import DriverLedgerEntry, DriverWithdrawalRequest
from driver_api.services import sync_wallet_from_ledger
from payments.models import UserAccount
from payments.payouts import services as payout_services
from payments.services.split_calculator import _create_ledger_entry


def auth_header_for(user):
    token = RefreshToken.for_user(user).access_token
    return {"HTTP_AUTHORIZATION": f"Bearer {str(token)}"}


@pytest.mark.django_db
def test_non_driver_cannot_access_dashboard(client):
    """Ensure non-driver users are forbidden from accessing the driver dashboard."""
    user = User.objects.create(email="nondriver@example.com", name="No Driver")
    response = client.get("/api/driver/dashboard/", **auth_header_for(user))
    assert response.status_code == 403


@pytest.mark.django_db
def test_driver_profile_endpoint(client):
    """Happy-path read of the driver profile API for an authenticated driver."""
    user = User.objects.create(email="driver1@example.com", name="Driver One")
    profile = DriverProfile.objects.create(user=user, first_name="Driver", last_name="One")
    response = client.get("/api/driver/profile/", **auth_header_for(user))
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["first_name"] == profile.first_name


@pytest.mark.django_db
def test_withdrawal_idempotency_key_returns_existing_record(client):
    """
    Driver withdrawal POST with the same Idempotency-Key should be idempotent:
    first call creates, second returns the same record instead of double-charging.
    """
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


@pytest.mark.django_db
def test_withdrawal_missing_idempotency_key_is_rejected(client):
    """Guardrail: withdrawal POST without Idempotency-Key must be rejected to avoid duplicate payouts."""
    user = User.objects.create(email="driver3@example.com", name="Driver Three")
    DriverProfile.objects.create(user=user, first_name="Driver", last_name="Three")

    response = client.post(
        "/api/driver/withdrawals/",
        data='{"amount":"100.00"}',
        content_type="application/json",
        **auth_header_for(user),
    )

    assert response.status_code == 400
    assert "Idempotency-Key" in response.json()["detail"]


@pytest.mark.django_db
def test_withdrawal_eligibility_endpoint_exposes_decision_snapshot(client, monkeypatch):
    """
    Eligibility endpoint should surface the unified decision snapshot so the app
    can show drivers exactly why they can or cannot withdraw.
    """
    user = User.objects.create(email="driver4@example.com", name="Driver Four")
    DriverProfile.objects.create(user=user, first_name="Driver", last_name="Four")

    decision = SimpleNamespace(
        eligible=True,
        minimum_amount=Decimal("1000.00"),
        max_amount=Decimal("5000.00"),
        available_balance=Decimal("5000.00"),
        checks={"bank_verified": True, "sufficient_balance": True},
    )

    monkeypatch.setattr("driver_api.views.evaluate_withdrawal_eligibility", lambda driver: decision)

    response = client.get("/api/driver/withdrawals/eligibility/", **auth_header_for(user))
    assert response.status_code == 200
    body = response.json()["data"]

    assert body["eligible"] is True
    assert body["minimum_amount"] == "1000.00"
    assert body["max_amount"] == "5000.00"
    assert body["available_balance"] == "5000.00"
    assert body["checks"]["bank_verified"] is True


@pytest.mark.django_db
def test_withdrawal_creation_triggers_background_processing_for_approved_request(client, monkeypatch):
    """
    When a new withdrawal is created in APPROVED state, the API should enqueue
    async processing instead of blocking the request thread.
    """
    user = User.objects.create(email="driver5@example.com", name="Driver Five")
    DriverProfile.objects.create(user=user, first_name="Driver", last_name="Five")

    created_calls = {"args": None}
    queued = {"count": 0}

    def fake_create_withdrawal_request(*, driver, amount, idempotency_key):
        created_calls["args"] = {"driver": driver, "amount": amount, "idempotency_key": idempotency_key}
        w = DriverWithdrawalRequest(
            id=1,
            driver=driver,
            amount=amount,
            idempotency_key=idempotency_key,
            status=DriverWithdrawalRequest.STATUS_APPROVED,
        )
        return w, True

    def fake_delay(withdrawal_id):
        queued["count"] += 1
        queued["last_id"] = withdrawal_id

    monkeypatch.setattr("driver_api.views.create_withdrawal_request", fake_create_withdrawal_request)
    monkeypatch.setattr("driver_api.views.process_withdrawal.delay", fake_delay)

    headers = {
        **auth_header_for(user),
        "HTTP_IDEMPOTENCY_KEY": "idem-xyz",
    }
    response = client.post(
        "/api/driver/withdrawals/",
        data='{"amount":"150.00"}',
        content_type="application/json",
        **headers,
    )

    assert response.status_code == 201
    assert queued["count"] == 1
    assert queued["last_id"] == 1


@pytest.mark.django_db
def test_sync_wallet_prefers_payments_ledger_when_available(monkeypatch):
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt")
    user = User.objects.create(email="driver6@example.com", name="Driver Six")
    profile = DriverProfile.objects.create(user=user, first_name="Driver", last_name="Six")
    UserAccount.objects.create(user=user, paystack_recipient_code="RCP_123")

    DriverLedgerEntry.objects.create(
        driver=profile,
        entry_type=DriverLedgerEntry.TYPE_CREDIT,
        amount="2000.00",
        source_type="legacy_seed",
        source_id="legacy-1",
        status=DriverLedgerEntry.STATUS_POSTED,
    )
    _create_ledger_entry(user=user, sale=None, role="driver", entry_type="credit", amount=500000, notes="seed")

    payout_services.create_withdrawal_request(
        user_id=str(user.id),
        amount_kobo=100000,
        role="driver",
        idempotency_key="idem-driver6",
        strategy="realtime",
    )

    wallet = sync_wallet_from_ledger(profile)

    assert wallet.current_balance == Decimal("5000.00")
    assert wallet.pending_balance == Decimal("1000.00")
    assert wallet.available_balance == Decimal("4000.00")
