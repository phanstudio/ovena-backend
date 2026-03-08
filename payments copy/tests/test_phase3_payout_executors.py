import pytest

from payments.models import User, Withdrawal
from payments.payouts.services import create_withdrawal_request, execute_batch, execute_realtime
from payments.services.split_calculator import _create_ledger_entry


@pytest.mark.django_db
def test_create_withdrawal_persists_strategy(monkeypatch):
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt")
    user = User.objects.create_user(username="s1", password="x", role="driver", paystack_recipient_code="RCP_1")
    _create_ledger_entry(user=user, sale=None, role=user.role, entry_type="credit", amount=500000, notes="seed")

    withdrawal, created = create_withdrawal_request(
        user_id=str(user.id),
        amount_kobo=100000,
        idempotency_key="idem-s1",
        strategy="realtime",
    )

    assert created is True
    assert withdrawal.strategy == Withdrawal.STRATEGY_REALTIME


@pytest.mark.django_db
def test_execute_realtime_sets_transfer_refs(monkeypatch):
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt")
    user = User.objects.create_user(username="s2", password="x", role="driver", paystack_recipient_code="RCP_2")
    _create_ledger_entry(user=user, sale=None, role=user.role, entry_type="credit", amount=500000, notes="seed")

    withdrawal, _ = create_withdrawal_request(
        user_id=str(user.id),
        amount_kobo=100000,
        idempotency_key="idem-s2",
        strategy="realtime",
    )

    def fake_initiate(payload):
        return {"data": {"reference": "TRX_REF_1", "transfer_code": "TRX_CODE_1"}}

    monkeypatch.setattr("payments.payouts.services.paystack_client.initiate_transfer", fake_initiate)

    execute_realtime(withdrawal)
    withdrawal.refresh_from_db()

    assert withdrawal.status == "processing"
    assert withdrawal.paystack_transfer_ref == "TRX_REF_1"
    assert withdrawal.paystack_transfer_code == "TRX_CODE_1"


@pytest.mark.django_db
def test_execute_batch_processes_only_batch_strategy(monkeypatch):
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt")
    user = User.objects.create_user(username="s3", password="x", role="driver", paystack_recipient_code="RCP_3")
    _create_ledger_entry(user=user, sale=None, role=user.role, entry_type="credit", amount=900000, notes="seed")

    batch_w, _ = create_withdrawal_request(
        user_id=str(user.id),
        amount_kobo=100000,
        idempotency_key="idem-s3-b",
        strategy="batch",
    )
    realtime_w, _ = create_withdrawal_request(
        user_id=str(user.id),
        amount_kobo=100000,
        idempotency_key="idem-s3-r",
        strategy="realtime",
    )

    def fake_bulk(payload):
        transfers = payload.get("transfers", [])
        return {
            "data": [
                {"reference": t.get("reference"), "transfer_code": f"BULK_{idx}"}
                for idx, t in enumerate(transfers)
            ]
        }

    monkeypatch.setattr("payments.payouts.services.paystack_client.bulk_transfer", fake_bulk)

    result = execute_batch()
    batch_w.refresh_from_db()
    realtime_w.refresh_from_db()

    assert result["count"] == 1
    assert batch_w.status == "processing"
    assert batch_w.paystack_transfer_code.startswith("BULK_")
    assert realtime_w.status == "pending_batch"
    assert realtime_w.paystack_transfer_code == ""

@pytest.mark.django_db
def test_mark_withdrawal_paid_and_failed_emit_metrics(monkeypatch):
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt")
    user = User.objects.create_user(username="s4", password="x", role="driver", paystack_recipient_code="RCP_4")
    _create_ledger_entry(user=user, sale=None, role=user.role, entry_type="credit", amount=500000, notes="seed")

    withdrawal, _ = create_withdrawal_request(
        user_id=str(user.id),
        amount_kobo=100000,
        idempotency_key="idem-s4",
        strategy="realtime",
    )

    metric_calls = []

    def fake_increment(name, value=1.0, tags=None):
        metric_calls.append((name, tags or {}))

    monkeypatch.setattr("payments.payouts.services.increment", fake_increment)

    from payments.payouts.services import mark_withdrawal_failed, mark_withdrawal_paid

    mark_withdrawal_paid(withdrawal)
    mark_withdrawal_failed(withdrawal, "test-failure")

    assert ("payments.payout.success_total", {"strategy": "realtime"}) in metric_calls
    assert ("payments.payout.failed_total", {"strategy": "realtime"}) in metric_calls
