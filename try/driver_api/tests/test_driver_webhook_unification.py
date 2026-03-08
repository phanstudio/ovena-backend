import pytest
from rest_framework.test import APIRequestFactory

from driver_api import tasks
from driver_api.views import PaystackWithdrawalWebhookView


@pytest.mark.django_db
def test_driver_webhook_delegates_to_shared_dispatcher(monkeypatch):
    captured = {}

    def fake_handle(*, payload_bytes, signature, parsed_body, transfer_only, request_id):
        captured["payload_bytes"] = payload_bytes
        captured["signature"] = signature
        captured["parsed_body"] = parsed_body
        captured["transfer_only"] = transfer_only
        captured["request_id"] = request_id
        return 200, "Webhook processed"

    monkeypatch.setattr("driver_api.views.handle_paystack_webhook", fake_handle)

    factory = APIRequestFactory()
    payload = {"event": "transfer.success", "data": {"reference": "abc"}}
    req = factory.post(
        "/api/driver/withdrawals/paystack/webhook/",
        payload,
        format="json",
        HTTP_X_PAYSTACK_SIGNATURE="sig",
        HTTP_X_REQUEST_ID="req-123",
    )

    response = PaystackWithdrawalWebhookView.as_view()(req)

    assert response.status_code == 200
    assert response.data["detail"] == "Webhook processed"
    assert captured["transfer_only"] is True
    assert captured["signature"] == "sig"
    assert captured["request_id"] == "req-123"


def test_reconcile_webhook_prefers_linked_payment_withdrawal_lookup(monkeypatch):
    withdrawal = object()

    class QuerySetStub:
        def __init__(self, result):
            self._result = result

        def select_related(self, *_args, **_kwargs):
            return self

        def first(self):
            return self._result

    class ManagerStub:
        def __init__(self):
            self.calls = []

        def filter(self, **kwargs):
            self.calls.append(kwargs)
            return QuerySetStub(withdrawal)

    manager = ManagerStub()
    monkeypatch.setattr(tasks.DriverWithdrawalRequest, "objects", manager)

    captured = {}

    def fake_mark_paid(arg):
        captured["withdrawal"] = arg

    monkeypatch.setattr(tasks, "mark_withdrawal_paid", fake_mark_paid)

    result = tasks.reconcile_paystack_webhook("trf-123", "success")

    assert result is withdrawal
    assert captured["withdrawal"] is withdrawal
    assert manager.calls == [{"payment_withdrawal__paystack_transfer_ref": "trf-123"}]
