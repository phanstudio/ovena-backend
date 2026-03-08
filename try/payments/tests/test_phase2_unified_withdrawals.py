import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from payments.models import PaymentIdempotencyKey, User, Withdrawal
from payments.payouts import services as payout_services
from payments.views import request_withdrawal_view
from payments.services.split_calculator import _create_ledger_entry


@pytest.mark.django_db
def test_create_withdrawal_request_unified_service(monkeypatch):
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt")
    user = User.objects.create_user(username="w1", password="x", role="driver", paystack_recipient_code="RCP_123")

    _create_ledger_entry(user=user, sale=None, role=user.role, entry_type="credit", amount=300000, notes="seed")

    withdrawal, created = payout_services.create_withdrawal_request(
        user_id=str(user.id), amount_kobo=120000, idempotency_key="idem-w1"
    )

    assert created is True
    assert withdrawal.status == "pending_batch"
    assert withdrawal.amount == 120000
    assert withdrawal.ledger_entry is not None


@pytest.mark.django_db
def test_create_withdrawal_request_idempotent(monkeypatch):
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt")
    user = User.objects.create_user(username="w2", password="x", role="driver", paystack_recipient_code="RCP_123")
    _create_ledger_entry(user=user, sale=None, role=user.role, entry_type="credit", amount=300000, notes="seed")

    first, created_first = payout_services.create_withdrawal_request(
        user_id=str(user.id), amount_kobo=120000, idempotency_key="idem-w2"
    )
    second, created_second = payout_services.create_withdrawal_request(
        user_id=str(user.id), amount_kobo=120000, idempotency_key="idem-w2"
    )

    assert created_first is True
    assert created_second is False
    assert first.id == second.id


@pytest.mark.django_db
def test_request_withdrawal_view_uses_unified_service_and_can_queue_realtime(monkeypatch):
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt")
    user = User.objects.create_user(username="w3", password="x", role="driver", paystack_recipient_code="RCP_123")
    _create_ledger_entry(user=user, sale=None, role=user.role, entry_type="credit", amount=300000, notes="seed")

    queued = {"calls": 0}

    def fake_delay(_withdrawal_id):
        queued["calls"] += 1

    monkeypatch.setattr("files.views.process_withdrawal.delay", fake_delay)

    factory = APIRequestFactory()
    req = factory.post(
        "/api/wallet/withdraw/",
        {"amount_kobo": 120000, "strategy": "realtime"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="idem-w3",
    )
    force_authenticate(req, user=user)
    res = request_withdrawal_view(req)

    assert res.status_code == 201
    assert res.data["strategy"] == "realtime"
    assert queued["calls"] == 1
    assert PaymentIdempotencyKey.objects.filter(scope="withdrawal_request", actor_id=str(user.id), key="idem-w3").exists()
    assert Withdrawal.objects.filter(user=user).count() == 1

@pytest.mark.django_db
def test_request_withdrawal_view_forwards_request_id_to_service(monkeypatch):
    user = User.objects.create_user(username="w4", password="x", role="driver")

    captured = {}

    class FakeWithdrawal:
        id = "11111111-1111-1111-1111-111111111111"
        amount = 120000
        status = "pending_batch"

    def fake_create_withdrawal_request(*, user_id, amount_kobo, idempotency_key, strategy, request_id):
        captured["user_id"] = user_id
        captured["amount_kobo"] = amount_kobo
        captured["idempotency_key"] = idempotency_key
        captured["strategy"] = strategy
        captured["request_id"] = request_id
        return FakeWithdrawal(), True

    monkeypatch.setattr("files.views.create_withdrawal_request", fake_create_withdrawal_request)

    factory = APIRequestFactory()
    req = factory.post(
        "/api/wallet/withdraw/",
        {"amount_kobo": 120000, "strategy": "batch"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="idem-w4",
        HTTP_X_REQUEST_ID="req-w4",
    )
    force_authenticate(req, user=user)
    res = request_withdrawal_view(req)

    assert res.status_code == 201
    assert captured["request_id"] == "req-w4"
    assert captured["idempotency_key"] == "idem-w4"
