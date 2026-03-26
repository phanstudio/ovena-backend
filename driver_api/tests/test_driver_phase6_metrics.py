from types import SimpleNamespace

from driver_api.unified_bridge import process_driver_withdrawal_with_payments
from driver_api.models import DriverWithdrawalRequest


def test_unified_bridge_increments_manual_review_metric_for_unverified_bank(monkeypatch):
    calls = []

    def fake_increment(name, value=1.0, tags=None):
        calls.append((name, value, tags or {}))

    monkeypatch.setattr("driver_api.unified_bridge.increment", fake_increment)

    class WithdrawalStub:
        status = DriverWithdrawalRequest.STATUS_APPROVED

        def __init__(self):
            self.driver = SimpleNamespace(bank_account=SimpleNamespace(is_verified=False))
            self.mark_failed_called = None

        def mark_failed(self, reason, manual=False):
            self.mark_failed_called = (reason, manual)

    w = WithdrawalStub()
    process_driver_withdrawal_with_payments(w, ensure_recipient_fn=lambda _bank: "RCP", max_retry_count=3)

    assert w.mark_failed_called == ("Driver bank account is not verified", True)
    assert any(name == "driver.withdrawal.manual_review_total" for name, _, _ in calls)


def test_unified_bridge_increments_retry_and_manual_on_exhausted_retries(monkeypatch):
    calls = []

    def fake_increment(name, value=1.0, tags=None):
        calls.append((name, value, tags or {}))

    monkeypatch.setattr("driver_api.unified_bridge.increment", fake_increment)

    class WithdrawalStub:
        status = DriverWithdrawalRequest.STATUS_APPROVED
        retry_count = 2

        def __init__(self):
            self.driver = SimpleNamespace(bank_account=SimpleNamespace(is_verified=True))

        def save(self, update_fields=None):
            return None

        def mark_failed(self, reason, manual=False):
            self.failed = (reason, manual)

    w = WithdrawalStub()
    process_driver_withdrawal_with_payments(
        w,
        ensure_recipient_fn=lambda _bank: (_ for _ in ()).throw(RuntimeError("boom")),
        max_retry_count=3,
    )

    assert w.failed == ("boom", True)
    metric_names = [name for name, _, _ in calls]
    assert "driver.withdrawal.retry_total" in metric_names
    assert "driver.withdrawal.manual_review_total" in metric_names
