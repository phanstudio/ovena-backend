from types import SimpleNamespace

from driver_api import services


def test_process_withdrawal_request_delegates_to_unified_bridge(monkeypatch):
    captured = {}

    sentinel = object()

    def fake_delegate(*, withdrawal, ensure_recipient_fn, max_retry_count):
        captured["withdrawal"] = withdrawal
        captured["ensure_recipient_fn"] = ensure_recipient_fn
        captured["max_retry_count"] = max_retry_count
        return sentinel

    monkeypatch.setattr(services, "process_driver_withdrawal_with_payments", fake_delegate)

    withdrawal = SimpleNamespace(id=1)
    result = services.process_withdrawal_request(withdrawal)

    assert result is sentinel
    assert captured["withdrawal"] is withdrawal
    assert callable(captured["ensure_recipient_fn"])
    assert captured["max_retry_count"] == services.MAX_RETRY_COUNT
