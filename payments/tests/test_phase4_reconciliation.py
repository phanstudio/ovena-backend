"""Phase 4: reconciliation between our ledger and Paystack.

Goals covered here:
- reconcile both batch and realtime withdrawals for a given run date;
- detect and classify mismatches by severity;
- trigger an alert hook with enough detail to investigate problems.
"""

from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone

from payments.models import User, Withdrawal
from payments.reconciliation.service import run_reconciliation


@pytest.mark.django_db
def test_reconcile_includes_batch_and_realtime(monkeypatch):
    """Happy-path reconciliation: both batch and realtime withdrawals are checked without mismatches."""
    run_date = date.today() - timedelta(days=1)
    aware_dt = timezone.make_aware(datetime.combine(run_date, time(12, 0)))

    user = User.objects.create_user(email="rec1@gmail.com", password="x")

    batch_w = Withdrawal.objects.create(
        user=user,
        amount=100000,
        status="processing",
        strategy=Withdrawal.STRATEGY_BATCH,
        batch_date=run_date,
        paystack_transfer_code="CODE_BATCH",
        paystack_transfer_ref="REF_BATCH",
        paystack_recipient_code="RCP_A",
    )
    realtime_w = Withdrawal.objects.create(
        user=user,
        amount=120000,
        status="complete",
        strategy=Withdrawal.STRATEGY_REALTIME,
        processed_at=aware_dt,
        paystack_transfer_code="CODE_RT",
        paystack_transfer_ref="REF_RT",
        paystack_recipient_code="RCP_B",
    )

    class FakeClient:
        def fetch_transfer(self, code):
            if code == "CODE_BATCH":
                return {"data": {"amount": 100000, "status": "pending", "recipient": {"recipient_code": "RCP_A"}}}
            if code == "CODE_RT":
                return {"data": {"amount": 120000, "status": "success", "recipient": {"recipient_code": "RCP_B"}}}
            return {"data": {}}

    monkeypatch.setattr("payments.reconciliation.service.PaystackClient", lambda: FakeClient())

    summary = run_reconciliation(run_date=run_date)

    assert summary["checked"] == 2
    assert summary["mismatches"] == 0
    batch_w.refresh_from_db()
    realtime_w.refresh_from_db()


@pytest.mark.django_db
def test_reconcile_classifies_severity_and_triggers_alert(monkeypatch):
    """When Paystack and local records diverge, mismatches are classified and surfaced via the alert callback."""
    run_date = date.today() - timedelta(days=1)
    user = User.objects.create_user(email="rec2@gmail.com", password="x")

    Withdrawal.objects.create(
        user=user,
        amount=100000,
        status="complete",
        strategy=Withdrawal.STRATEGY_BATCH,
        batch_date=run_date,
        paystack_transfer_code="CODE_BAD",
        paystack_transfer_ref="REF_BAD",
        paystack_recipient_code="RCP_LOCAL",
    )

    class FakeClient:
        def fetch_transfer(self, _code):
            return {
                "data": {
                    "amount": 90000,
                    "status": "failed",
                    "recipient": {"recipient_code": "RCP_REMOTE"},
                }
            }

    monkeypatch.setattr("payments.reconciliation.service.PaystackClient", lambda: FakeClient())

    captured = {"called": False, "mismatches": []}

    def fake_alert(summary, mismatches):
        captured["called"] = True
        captured["mismatches"] = mismatches

    summary = run_reconciliation(run_date=run_date, alert_callback=fake_alert)

    assert summary["mismatches"] >= 2
    assert captured["called"] is True
    severities = {m["severity"] for m in captured["mismatches"]}
    assert "critical" in severities or "high" in severities
