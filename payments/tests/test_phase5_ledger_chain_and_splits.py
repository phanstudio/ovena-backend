import pytest
from unittest.mock import patch
from django.utils import timezone
from payments.models import User, Sale, LedgerEntry, Withdrawal
from payments.services.split_calculator import (
    calculate_split,
    order_v1_split,
    percent_split,
    credit_all_parties,
    reverse_ledger_entries,
    _create_ledger_entry,
)
from payments.services.ledger_audit import (
    verify_user_ledger_chain_since_last_withdrawal,
    flag_withdrawal,
)


@pytest.mark.django_db
def test_ledger_hash_chain_linking(monkeypatch):
    """Ledger entries for a user should form an unbroken hash chain with previous_hash."""
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt-secret")
    user = User.objects.create_user(email="chain_user@test.com", password="x")

    e1 = _create_ledger_entry(user=user, sale=None, role="driver", entry_type="credit", amount=10000, notes="First")
    assert e1.previous_hash == "GENESIS"
    assert e1.balance_after == 10000
    assert e1.verify_hash() is True

    e2 = _create_ledger_entry(user=user, sale=None, role="driver", entry_type="credit", amount=25000, notes="Second")
    assert e2.previous_hash == e1.row_hash
    assert e2.balance_after == 35000
    assert e2.verify_hash() is True

    e3 = _create_ledger_entry(user=user, sale=None, role="driver", entry_type="debit", amount=-5000, notes="Third")
    assert e3.previous_hash == e2.row_hash
    assert e3.balance_after == 30000
    assert e3.verify_hash() is True

    valid, reason, failed = verify_user_ledger_chain_since_last_withdrawal(user)
    assert valid is True
    assert failed == []


@pytest.mark.django_db
def test_ledger_chain_tamper_detection(monkeypatch):
    """Tampering with an entry's amount directly in DB breaks the hash and is detected by audit."""
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt-secret")
    user = User.objects.create_user(email="tamper_user@test.com", password="x")

    e1 = _create_ledger_entry(user=user, sale=None, role="driver", entry_type="credit", amount=10000)
    e2 = _create_ledger_entry(user=user, sale=None, role="driver", entry_type="credit", amount=20000)

    # Directly bypass save() immutability by using queryset update to simulate DB tampering
    LedgerEntry.objects.filter(id=e2.id).update(amount=999999)

    valid, reason, failed = verify_user_ledger_chain_since_last_withdrawal(user)
    assert valid is False
    assert str(e2.id) in failed


@pytest.mark.django_db
def test_flag_withdrawal_quarantine_and_ticket(monkeypatch):
    """Flagging a withdrawal sets security cooldown and creates a support ticket."""
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt-secret")
    user = User.objects.create_user(email="flag_user@test.com", password="x")
    withdrawal = Withdrawal.objects.create(
        user=user,
        amount=50000,
        status="pending_batch",
    )

    ticket_created = []

    def fake_ticket(**kwargs):
        ticket_created.append(kwargs)

    monkeypatch.setattr("support_center.task.create_system_ticket", fake_ticket)

    flag_withdrawal(withdrawal, reason="Hash chain discrepancy detected", failed_entry_ids=["fake-id-1"])

    withdrawal.refresh_from_db()
    assert withdrawal.is_flagged is True
    assert "Hash chain discrepancy detected" in withdrawal.flag_reason
    assert len(ticket_created) == 1
    assert ticket_created[0]["category"] == "security"


@pytest.mark.django_db
def test_credit_all_parties_delivery_fee_refund_when_no_driver(monkeypatch):
    """When sale has no driver and not picked up, delivery fee is routed to customer as credit."""
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt-secret")
    customer = User.objects.create_user(email="cust@test.com", password="x")
    biz_owner = User.objects.create_user(email="biz@test.com", password="x")

    sale = Sale.objects.create(
        reference="REF-SPLIT-101",
        payer=customer,
        business_owner=biz_owner,
        driver=None,
        total_amount=150000,
    )

    split = {
        "amounts": {
            "business_owner": 100000,
            "driver": 30000,
            "platform": 20000,
            "referral": 0,
        }
    }

    credit_all_parties(sale, split, picked_up=False)

    biz_entry = LedgerEntry.objects.get(sale=sale, role="business_owner")
    assert biz_entry.amount == 100000
    assert biz_entry.user == biz_owner

    cust_entry = LedgerEntry.objects.get(sale=sale, role="customer")
    assert cust_entry.amount == 30000
    assert cust_entry.user == customer


@pytest.mark.django_db
def test_reverse_ledger_entries_is_idempotent(monkeypatch):
    """Calling reverse_ledger_entries multiple times does not produce duplicate reversals."""
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt-secret")
    customer = User.objects.create_user(email="rev_cust@test.com", password="x")
    biz_owner = User.objects.create_user(email="rev_biz@test.com", password="x")

    sale = Sale.objects.create(
        reference="REF-SPLIT-102",
        payer=customer,
        business_owner=biz_owner,
        total_amount=100000,
    )

    split = {
        "amounts": {
            "business_owner": 80000,
            "driver": 0,
            "platform": 20000,
            "referral": 0,
        }
    }
    credit_all_parties(sale, split, picked_up=True)

    # First reversal
    reverse_ledger_entries(sale, reason="Customer cancelled", responsible_party="business")
    reversals_1 = LedgerEntry.objects.filter(sale=sale, type="reversal").count()
    assert reversals_1 == 1

    # Second reversal - should skip existing reversal
    reverse_ledger_entries(sale, reason="Customer cancelled duplicate call", responsible_party="business")
    reversals_2 = LedgerEntry.objects.filter(sale=sale, type="reversal").count()
    assert reversals_2 == 1


def test_order_v1_split_negative_platform_guard():
    """Negative platform fee must raise ValueError."""
    meta = {
        "items_total_kobo": 100000,
        "delivery_fee_kobo": 20000,
    }
    with pytest.raises(ValueError, match="total_amount .* is less than"):
        order_v1_split(total_amount=110000, has_referral=False, meta=meta)


def test_percent_split_basis_points():
    """Integer basis points avoid float drift."""
    config = {
        "platform_cut_percent": 15.0,
        "driver_cut_percent": 10.0,
        "business_owner_cut_percent": 75.0,
        "referral_cut_percent": 0.0,
    }
    res = percent_split(total_amount=100000, has_referral=False, config=config)
    assert res["amounts"]["driver"] == 10000
    assert res["amounts"]["business_owner"] == 75000
    assert res["amounts"]["platform"] == 15000
    assert sum(res["amounts"].values()) == 100000
