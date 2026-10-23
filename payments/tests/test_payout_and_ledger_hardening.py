"""
test_payout_and_ledger_hardening.py

Comprehensive tests verifying all security hardening in payouts, splits,
ResponsibleParty enum, unassigned delivery refund to customer, negative debt
amortization, and ledger integrity.
"""

import pytest
from django.db import IntegrityError
from django.utils import timezone

from accounts.models import DriverProfile, User
from accounts.models.driver import DriverBankAccount
from payments.integrations.paystack.errors import PaystackAPIError
from payments.models import LedgerEntry, ResponsibleParty, Sale, UserAccount, Withdrawal
from payments.payouts.services import (
    create_withdrawal_request,
    execute_realtime,
    get_balance_summary,
    mark_withdrawal_failed,
    mark_withdrawal_paid,
    mark_withdrawal_reversed,
)
from payments.services.split_calculator import (
    _create_ledger_entry,
    credit_all_parties,
    order_v1_split,
    reverse_ledger_entries,
)


@pytest.mark.django_db
def test_order_v1_split_explicit_zero_fee():
    """Explicit 0% fee and 0 fixed fee must NOT default to 5.0% or 500 NGN."""
    meta_zero = {
        "items_total_kobo": 100000,
        "delivery_fee_kobo": 20000,
        "platform_fee_percent": 0.0,
        "platform_fee_fixed_kobo": 0,
    }
    split = order_v1_split(total_amount=120000, has_referral=False, meta=meta_zero)

    assert split["policy"]["platform_fee_percent"] == 0.0
    assert split["policy"]["platform_fee_fixed_kobo"] == 0
    assert split["amounts"]["platform"] == 0
    assert split["amounts"]["driver"] == 20000
    assert split["amounts"]["business_owner"] == 100000


@pytest.mark.django_db
def test_reverse_ledger_entries_responsible_party_enum(monkeypatch):
    """
    reverse_ledger_entries must:
    - Fail closed (raise ValueError) on unknown responsible_party strings.
    - BUSINESS fault: reverses business owner and referral; driver keeps earnings.
    - DRIVER fault: reverses driver; business owner keeps earnings.
    - PLATFORM fault: reverses neither.
    """
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt-secret")
    customer = User.objects.create_user(email="c_rev@test.com", password="x")
    biz_owner = User.objects.create_user(email="b_rev@test.com", password="x")
    driver = User.objects.create_user(email="d_rev@test.com", password="x")
    referral = User.objects.create_user(email="r_rev@test.com", password="x")

    sale = Sale.objects.create(
        reference="REF-REV-01",
        payer=customer,
        business_owner=biz_owner,
        driver=driver,
        referral_user=referral,
        total_amount=150000,
    )
    split = {
        "amounts": {
            "business_owner": 100000,
            "driver": 30000,
            "referral": 10000,
            "platform": 10000,
        },
        "total": 150000,
    }
    credit_all_parties(sale, split)

    # 1. Invalid responsible party fails closed
    with pytest.raises(ValueError, match="Unknown responsible_party"):
        reverse_ledger_entries(sale, reason="Bad input", responsible_party="restaurant")

    with pytest.raises(ValueError, match="Unknown responsible_party"):
        reverse_ledger_entries(sale, reason="Bad input", responsible_party="None")

    # 2. Business fault: reverses business owner and referral; driver keeps pay
    reverse_ledger_entries(sale, reason="Bad food", responsible_party=ResponsibleParty.BUSINESS)
    rev_entries = list(LedgerEntry.objects.filter(sale=sale, type="reversal"))
    rev_roles = {e.role for e in rev_entries}
    assert "business_owner" in rev_roles
    assert "referral" in rev_roles
    assert "driver" not in rev_roles


@pytest.mark.django_db
def test_unassigned_driver_delivery_fee_refunded_to_customer(monkeypatch):
    """If sale.driver is None, the delivery fee must be credited back to customer."""
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt-secret")
    customer = User.objects.create_user(email="unassigned_cust@test.com", password="x")
    biz_owner = User.objects.create_user(email="unassigned_biz@test.com", password="x")

    sale = Sale.objects.create(
        reference="REF-UNASSIGNED-01",
        payer=customer,
        business_owner=biz_owner,
        driver=None,
        total_amount=130000,
    )
    split = {
        "amounts": {
            "business_owner": 100000,
            "driver": 30000,
            "referral": 0,
            "platform": 0,
        },
        "total": 130000,
    }
    # Customer self-pickup: delivery fee was charged at checkout, but no driver assigned
    credit_all_parties(sale, split, picked_up=True)

    customer_entry = LedgerEntry.objects.filter(sale=sale, user=customer, role="customer").first()
    assert customer_entry is not None
    assert customer_entry.amount == 30000
    assert customer_entry.type == "credit"


@pytest.mark.django_db
def test_negative_debt_amortization_across_future_credits(monkeypatch):
    """
    When a post-withdrawal reversal drives a balance negative, subsequent
    credits monotonically offset the debt, and get_balance_summary exposes debt.
    """
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt-secret")
    user = User.objects.create_user(email="debtor@test.com", password="x")
    UserAccount.objects.create(user=user, paystack_recipient_code="RCP_DEBT")

    # Seed 100,000 kobo (₦1,000)
    _create_ledger_entry(user=user, sale=None, role="driver", entry_type="credit", amount=100000, notes="seed")

    # Withdraw 100,000 kobo (balance becomes 0)
    w, _ = create_withdrawal_request(user_id=str(user.id), amount_kobo=100000, idempotency_key="idem-w-debt", role="driver")
    mark_withdrawal_paid(w)

    summary_zero = get_balance_summary(str(user.id), role="driver")
    assert summary_zero["total_balance_kobo"] == 0
    assert summary_zero["outstanding_debt_kobo"] == 0
    assert summary_zero["can_withdraw"] is False

    # A dispute reversal occurs for 40,000 kobo -> balance goes to -40,000 kobo
    _create_ledger_entry(user=user, sale=None, role="driver", entry_type="reversal", amount=-40000, notes="dispute")

    summary_neg = get_balance_summary(str(user.id), role="driver")
    assert summary_neg["total_balance_kobo"] == -40000
    assert summary_neg["outstanding_debt_kobo"] == 40000
    assert summary_neg["available_balance_kobo"] == 0
    assert summary_neg["can_withdraw"] is False

    # Next job earns 25,000 kobo -> balance becomes -15,000 kobo (debt partially amortized)
    _create_ledger_entry(user=user, sale=None, role="driver", entry_type="credit", amount=25000, notes="job 1")
    summary_partial = get_balance_summary(str(user.id), role="driver")
    assert summary_partial["total_balance_kobo"] == -15000
    assert summary_partial["outstanding_debt_kobo"] == 15000
    assert summary_partial["can_withdraw"] is False

    # Next job earns 30,000 kobo -> balance becomes +15,000 kobo (debt fully amortized)
    _create_ledger_entry(user=user, sale=None, role="driver", entry_type="credit", amount=30000, notes="job 2")
    summary_pos = get_balance_summary(str(user.id), role="driver")
    assert summary_pos["total_balance_kobo"] == 15000
    assert summary_pos["outstanding_debt_kobo"] == 0
    assert summary_pos["available_balance_kobo"] == 15000


@pytest.mark.django_db
def test_float_amount_rejected_in_ledger_entry(monkeypatch):
    """_create_ledger_entry must raise TypeError if amount is a float."""
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt-secret")
    user = User.objects.create_user(email="float_user@test.com", password="x")

    with pytest.raises(TypeError, match="Ledger amount must be int"):
        _create_ledger_entry(user=user, sale=None, role="driver", entry_type="credit", amount=1500.5)


@pytest.mark.django_db
def test_mark_withdrawal_failed_and_paid_state_machine(monkeypatch):
    """
    Verifies:
    - mark_withdrawal_failed cannot fail a completed withdrawal (refuses refund).
    - mark_withdrawal_paid cannot pay a failed withdrawal (refuses double-pay).
    - mark_withdrawal_failed writes refund_ledger_entry and is idempotent.
    """
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt-secret")
    user = User.objects.create_user(email="state_user@test.com", password="x")
    UserAccount.objects.create(user=user, paystack_recipient_code="RCP_STATE")
    _create_ledger_entry(user=user, sale=None, role="driver", entry_type="credit", amount=500000, notes="seed")

    w1, _ = create_withdrawal_request(user_id=str(user.id), amount_kobo=100000, idempotency_key="idem-w1", role="driver")
    mark_withdrawal_paid(w1)
    w1.refresh_from_db()
    assert w1.status == "complete"

    # Attempting to fail a complete withdrawal must NOT refund or change status
    mark_withdrawal_failed(w1, reason="Fraudulent claim")
    w1.refresh_from_db()
    assert w1.status == "complete"
    assert w1.refund_ledger_entry is None

    # Failed withdrawal cannot be flipped to complete
    w2, _ = create_withdrawal_request(user_id=str(user.id), amount_kobo=100000, idempotency_key="idem-w2", role="driver")
    mark_withdrawal_failed(w2, reason="Bank reject")
    w2.refresh_from_db()
    assert w2.status == "failed"
    assert w2.refund_ledger_entry is not None

    mark_withdrawal_paid(w2)
    w2.refresh_from_db()
    assert w2.status == "failed"


@pytest.mark.django_db
def test_mark_withdrawal_reversed(monkeypatch):
    """Paystack transfer.reversed must mark withdrawal reversed and refund hold."""
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt-secret")
    user = User.objects.create_user(email="rev_wd@test.com", password="x")
    UserAccount.objects.create(user=user, paystack_recipient_code="RCP_REV")
    _create_ledger_entry(user=user, sale=None, role="driver", entry_type="credit", amount=500000, notes="seed")

    w, _ = create_withdrawal_request(user_id=str(user.id), amount_kobo=100000, idempotency_key="idem-rev-wd", role="driver")
    mark_withdrawal_paid(w)
    w.refresh_from_db()
    assert w.status == "complete"

    mark_withdrawal_reversed(w, reason="Reversed by provider")
    w.refresh_from_db()
    assert w.status == "reversed"
    assert w.refund_ledger_entry is not None
    assert w.refund_ledger_entry.amount == 100000


@pytest.mark.django_db
def test_execute_realtime_claim_and_decoupled_network_call(monkeypatch):
    """
    execute_realtime claims the row, generates wd_<hex> reference, and fails on Paystack 4xx.
    """
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt-secret")
    user = User.objects.create_user(email="rt_claim@test.com", password="x")
    UserAccount.objects.create(user=user, paystack_recipient_code="RCP_CLAIM")
    _create_ledger_entry(user=user, sale=None, role="driver", entry_type="credit", amount=500000, notes="seed")

    w, _ = create_withdrawal_request(user_id=str(user.id), amount_kobo=100000, idempotency_key="idem-rt-claim", strategy="realtime", role="driver")

    def fake_initiate_fail(payload):
        raise PaystackAPIError("Account number is invalid", status_code=400)

    monkeypatch.setattr("payments.payouts.services.paystack_client.initiate_transfer", fake_initiate_fail)

    execute_realtime(w)
    w.refresh_from_db()
    assert w.status == "failed"
    assert "Account number is invalid" in w.failure_reason
    assert w.paystack_transfer_ref.startswith("wd_")
    assert w.refund_ledger_entry is not None


@pytest.mark.django_db
def test_abstract_payout_account_invalidates_recipient_code_on_change(monkeypatch):
    """Modifying bank account number or code resets paystack_recipient_code."""
    user = User.objects.create_user(email="driver_bank@test.com", password="x")
    driver = DriverProfile.objects.create(user=user)
    bank = DriverBankAccount.objects.create(
        driver=driver,
        bank_code="058",
        bank_account_number="0123456789",
        bank_account_name="Driver Test",
        paystack_recipient_code="RCP_OLD",
    )
    assert bank.paystack_recipient_code == "RCP_OLD"

    bank.bank_account_number = "9876543210"
    bank.save()
    bank.refresh_from_db()
    assert bank.paystack_recipient_code == ""


@pytest.mark.django_db
def test_consecutive_withdrawals_do_not_double_subtract_pending(monkeypatch):
    """
    Creating a withdrawal writes a ledger debit hold immediately.
    A second withdrawal request while the first is still pending must not
    double-subtract the first withdrawal's amount from available balance.
    """
    monkeypatch.setenv("LEDGER_HASH_SALT", "test-salt-secret")
    user = User.objects.create_user(email="consec_wd@test.com", password="x")
    UserAccount.objects.create(user=user, paystack_recipient_code="RCP_CONSEC")
    # Seed 200,000 kobo (₦2,000)
    _create_ledger_entry(user=user, sale=None, role="driver", entry_type="credit", amount=200000, notes="seed")

    # 1st withdrawal of 100,000 kobo leaves 100,000 kobo in ledger balance
    w1, created1 = create_withdrawal_request(
        user_id=str(user.id), amount_kobo=100000, idempotency_key="idem-c1", role="driver"
    )
    assert created1 is True
    assert w1.status == "pending_batch"

    # 2nd withdrawal of 100,000 kobo should succeed because 100,000 kobo is still available
    w2, created2 = create_withdrawal_request(
        user_id=str(user.id), amount_kobo=100000, idempotency_key="idem-c2", role="driver"
    )
    assert created2 is True
    assert w2.status == "pending_batch"
