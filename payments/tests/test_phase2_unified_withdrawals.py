"""Phase 2: unified withdrawals and wallet API.

These tests verify that:
- withdrawals are created through the central payouts service (not direct Paystack calls);
- idempotency for withdrawal requests is enforced at the service layer;
- the public wallet/withdraw API uses the unified service, queues work, and tracks idempotency keys.
"""

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import Business, BusinessAdmin, BusinessPayoutAccount
from payments.models import PaymentIdempotencyKey, User, UserAccount, Withdrawal
from payments.payouts import services as payout_services
from payments.payouts.tasks import ensure_paystack_recipient_for_business_admin
from payments.views import request_withdrawal_view
from payments.services.split_calculator import _create_ledger_entry


@pytest.mark.django_db
def test_create_withdrawal_request_unified_service(monkeypatch):
    """Baseline: a withdrawal created through the unified payouts service is persisted with a hold entry."""
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt")
    user = User.objects.create_user(email="w1@gmail.com", password="x", role="driver")
    UserAccount.objects.create(user=user, paystack_recipient_code="RCP_123")

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
    """A second call with the same (user, idempotency key) should return the same withdrawal instead of duplicating."""
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt")
    user = User.objects.create_user(email="w2@gmail.com", password="x", role="driver")
    UserAccount.objects.create(user=user, paystack_recipient_code="RCP_123")
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
    """Wallet API should call the unified service and enqueue realtime payouts asynchronously."""
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt")
    user = User.objects.create_user(email="w3@gmail.com", password="x", role="driver")
    UserAccount.objects.create(user=user, paystack_recipient_code="RCP_123")
    _create_ledger_entry(user=user, sale=None, role=user.role, entry_type="credit", amount=300000, notes="seed")

    queued = {"calls": 0}

    def fake_delay(_withdrawal_id):
        queued["calls"] += 1

    monkeypatch.setattr("payments.views.process_withdrawal.delay", fake_delay)

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
    """`X-Request-ID` and idempotency key from the API layer are forwarded into the core service for tracing."""
    user = User.objects.create_user(email="w4@gmail.com", password="x", role="driver")

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

    monkeypatch.setattr("payments.views.create_withdrawal_request", fake_create_withdrawal_request)

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


@pytest.mark.django_db
def test_business_admin_can_create_withdrawal_request(monkeypatch):
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt")
    user = User.objects.create_user(email="biz1@gmail.com", password="x", role="businessadmin")
    UserAccount.objects.create(user=user, paystack_recipient_code="RCP_BIZ_1")
    _create_ledger_entry(user=user, sale=None, role="business_owner", entry_type="credit", amount=500000, notes="seed")

    withdrawal, created = payout_services.create_withdrawal_request(
        user_id=str(user.id), amount_kobo=200000, idempotency_key="idem-biz1"
    )

    assert created is True
    assert withdrawal.status == "pending_batch"
    assert withdrawal.ledger_entry is not None
    assert withdrawal.ledger_entry.role == "business_owner"


@pytest.mark.django_db
def test_business_admin_payout_account_syncs_to_user_account(monkeypatch):
    user = User.objects.create_user(email="biz2@gmail.com", password="x", role="businessadmin")
    business = Business.objects.create(business_name="Biz Two")
    admin = BusinessAdmin.objects.create(user=user, business=business)
    monkeypatch.setattr("payments.payouts.tasks.ensure_paystack_recipient_for_business_admin.delay", lambda *_args, **_kwargs: None)
    BusinessPayoutAccount.objects.create(
        business=business,
        bank_name="GTBank",
        bank_code="058",
        account_number="0123456789",
        account_name="Biz Two Ltd",
        bvn="1234",
    )

    monkeypatch.setattr(
        "payments.payouts.tasks.PaystackClient.create_transfer_recipient",
        lambda self, payload: {"data": {"recipient_code": "RCP_BIZ_2"}},
    )

    code = ensure_paystack_recipient_for_business_admin(admin.id)
    account = UserAccount.objects.get(user=user)

    assert code == "RCP_BIZ_2"
    assert account.paystack_recipient_code == "RCP_BIZ_2"
    assert account.bank_code == "058"
    assert account.bank_account_number == "0123456789"
