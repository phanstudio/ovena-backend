"""Phase 1: idempotency and webhook plumbing for the payments app.

These tests focus on:
- protecting `sales.initialize` with idempotency keys so callers can safely retry;
- de-duping Paystack webhooks while still recording every attempt;
- wiring transfer webhooks into the unified withdrawal + driver sync pipeline;
- emitting basic observability metrics around webhook lag and outcomes.
"""

import hashlib
import hmac
import json

import pytest
from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from payments.models import PaystackWebhookLog, PaymentIdempotencyKey, User
from payments import views as payment_views
import payments.webhooks.paystack as paystack_webhooks


@pytest.mark.django_db
@override_settings(PAYSTACK_SECRET_KEY="sk_test_secret")
def test_idempotent_request_replay_returns_saved_response(monkeypatch):
    """Same initialize-sale request + idempotency key must reuse the first stored response."""
    factory = APIRequestFactory()
    user = User.objects.create_user(email="u1@gmail.com", password="x")

    call_count = {"n": 0}

    def fake_initialize_sale(**kwargs):
        call_count["n"] += 1
        return {"sale_id": "s1", "payment_url": "https://paystack/checkout"}

    monkeypatch.setattr(payment_views, "initialize_sale", fake_initialize_sale)

    payload = {"business_owner_id": str(user.id), "amount_kobo": 10000, "metadata": {}}

    req1 = factory.post("/api/sales/initialize/", payload, format="json", HTTP_IDEMPOTENCY_KEY="idem-a")
    force_authenticate(req1, user=user)
    res1 = payment_views.initialize_sale_view(req1)

    req2 = factory.post("/api/sales/initialize/", payload, format="json", HTTP_IDEMPOTENCY_KEY="idem-a")
    force_authenticate(req2, user=user)
    res2 = payment_views.initialize_sale_view(req2)

    assert res1.status_code == 201
    assert res2.status_code == 200
    assert res1.data == res2.data
    assert call_count["n"] == 1
    assert PaymentIdempotencyKey.objects.count() == 1


@pytest.mark.django_db
@override_settings(PAYSTACK_SECRET_KEY="sk_test_secret")
def test_idempotency_conflict_on_payload_mismatch(monkeypatch):
    """Re-using an idempotency key with a different payload should be rejected to avoid ambiguity."""
    factory = APIRequestFactory()
    user = User.objects.create_user(email="u2@gmail.com", password="x")

    monkeypatch.setattr(payment_views, "initialize_sale", lambda **kwargs: {"sale_id": "s2"})

    req1 = factory.post(
        "/api/sales/initialize/",
        {"business_owner_id": str(user.id), "amount_kobo": 10000, "metadata": {}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="idem-b",
    )
    force_authenticate(req1, user=user)
    res1 = payment_views.initialize_sale_view(req1)

    req2 = factory.post(
        "/api/sales/initialize/",
        {"business_owner_id": str(user.id), "amount_kobo": 20000, "metadata": {}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="idem-b",
    )
    force_authenticate(req2, user=user)
    res2 = payment_views.initialize_sale_view(req2)

    assert res1.status_code == 201
    assert res2.status_code == 409
    assert "different payload" in res2.data["error"].lower()


@pytest.mark.django_db
@override_settings(PAYSTACK_SECRET_KEY="sk_test_secret")
def test_webhook_replay_dedup(monkeypatch):
    """Identical Paystack webhooks should be processed once and treated as replays thereafter."""
    factory = APIRequestFactory()

    call_count = {"n": 0}

    def fake_process_webhook(body):
        call_count["n"] += 1

    monkeypatch.setattr(paystack_webhooks, "process_event", fake_process_webhook)

    payload = {
        "event": "charge.success",
        "data": {"id": 12345, "reference": "sale-ref-1", "amount": 10000},
    }
    raw = json.dumps(payload).encode("utf-8")
    signature = hmac.new(b"sk_test_secret", raw, hashlib.sha512).hexdigest()

    req1 = factory.post("/api/webhooks/paystack/",raw,content_type="application/json",HTTP_X_PAYSTACK_SIGNATURE=signature)
    res1 = payment_views.paystack_webhook_view(req1)

    req2 = factory.post("/api/webhooks/paystack/",raw,content_type="application/json",HTTP_X_PAYSTACK_SIGNATURE=signature)
    res2 = payment_views.paystack_webhook_view(req2)

    assert res1.status_code == 200
    assert res2.status_code == 200
    assert call_count["n"] == 1
    assert PaystackWebhookLog.objects.count() == 1
    assert PaystackWebhookLog.objects.first().processed is True


@pytest.mark.django_db
@override_settings(PAYSTACK_SECRET_KEY="sk_test_secret")
def test_webhook_processed_and_error_transitions(monkeypatch):
    """Webhook logs should capture failures, then transition to processed once the handler succeeds."""
    factory = APIRequestFactory()

    payload = {
        "event": "charge.success",
        "data": {"id": 999, "reference": "sale-ref-err", "amount": 10000},
    }
    raw = json.dumps(payload).encode("utf-8")
    signature = hmac.new(b"sk_test_secret", raw, hashlib.sha512).hexdigest()

    def fail_once(_body):
        raise RuntimeError("boom")

    monkeypatch.setattr(paystack_webhooks, "process_event", fail_once)

    req1 = factory.post("/api/webhooks/paystack/",raw,content_type="application/json",HTTP_X_PAYSTACK_SIGNATURE=signature)
    res1 = payment_views.paystack_webhook_view(req1)

    log = PaystackWebhookLog.objects.get(event_id="999")
    assert res1.status_code == 200
    assert log.processed is False
    assert "boom" in log.error_reason

    monkeypatch.setattr(paystack_webhooks, "process_event", lambda _body: None)
    req2 = factory.post("/api/webhooks/paystack/",raw,content_type="application/json",HTTP_X_PAYSTACK_SIGNATURE=signature)
    res2 = payment_views.paystack_webhook_view(req2)

    log.refresh_from_db()
    assert res2.status_code == 200
    assert log.processed is True
    assert log.processed_at is not None
    assert log.error_reason == ""




def test_transfer_event_syncs_driver_via_link_and_skips_fallback_reconcile(monkeypatch):
    """Happy-path transfer.success: update payments.Withdrawal and sync linked driver withdrawal, no fallback reconcile."""
    payment_withdrawal = object()
    called = {"paid": 0, "sync": 0, "reconcile": 0}

    monkeypatch.setattr(paystack_webhooks, "_find_payment_withdrawal", lambda **kwargs: payment_withdrawal)

    def fake_paid(_withdrawal):
        called["paid"] += 1

    def fake_sync(**kwargs):
        called["sync"] += 1
        return True

    def fake_reconcile(**kwargs):
        called["reconcile"] += 1

    monkeypatch.setattr(paystack_webhooks, "mark_withdrawal_paid", fake_paid)
    monkeypatch.setattr(paystack_webhooks, "_sync_driver_withdrawal_from_linked_payment", fake_sync)
    monkeypatch.setattr(paystack_webhooks, "_reconcile_driver_withdrawal", fake_reconcile)

    paystack_webhooks.process_event(
        {
            "event": "transfer.success",
            "data": {"reference": "ref-1", "transfer_code": "trf-1"},
        }
    )

    assert called == {"paid": 1, "sync": 1, "reconcile": 0}


def test_transfer_event_falls_back_to_reconcile_when_link_sync_not_available(monkeypatch):
    """When no linked driver record is found, Paystack transfer events should fall back to reconcile-based resolution."""
    payment_withdrawal = object()
    captured = {}

    monkeypatch.setattr(paystack_webhooks, "_find_payment_withdrawal", lambda **kwargs: payment_withdrawal)

    def fake_failed(_withdrawal, reason):
        captured["reason"] = reason

    monkeypatch.setattr(paystack_webhooks, "mark_withdrawal_failed", fake_failed)
    monkeypatch.setattr(paystack_webhooks, "_sync_driver_withdrawal_from_linked_payment", lambda **kwargs: False)

    def fake_reconcile(**kwargs):
        captured["reconcile"] = kwargs

    monkeypatch.setattr(paystack_webhooks, "_reconcile_driver_withdrawal", fake_reconcile)

    paystack_webhooks.process_event(
        {
            "event": "transfer.failed",
            "data": {"reference": "", "transfer_code": "trf-fallback", "gateway_response": "declined"},
        }
    )

    assert captured["reason"] == "declined"
    assert captured["reconcile"] == {
        "transfer_reference": "trf-fallback",
        "transfer_status": "failed",
        "reason": "declined",
    }

@pytest.mark.django_db
@override_settings(PAYSTACK_SECRET_KEY="sk_test_secret")
def test_webhook_lag_metric_is_recorded(monkeypatch):
    """We track end-to-end webhook processing lag to monitor operational health."""
    captured = {"calls": []}

    def fake_observe(name, value_ms, tags=None):
        captured["calls"].append((name, value_ms, tags or {}))

    monkeypatch.setattr(paystack_webhooks, "observe_ms", fake_observe)

    payload = {
        "event": "transfer.success",
        "data": {
            "id": 321,
            "reference": "lag-ref-1",
            "created_at": "2024-01-01T00:00:00Z",
        },
    }
    raw = json.dumps(payload).encode("utf-8")
    signature = hmac.new(b"sk_test_secret", raw, hashlib.sha512).hexdigest()

    status_code, _detail = paystack_webhooks.handle_paystack_webhook(
        payload_bytes=raw,
        signature=signature,
        parsed_body=payload,
        transfer_only=False,
        request_id="req-lag-1",
    )

    assert status_code == 200
    assert captured["calls"]
    metric_name, metric_value, metric_tags = captured["calls"][0]
    assert metric_name == "payments.webhook.processing_lag_ms"
    assert metric_value >= 0
    assert metric_tags.get("event") == "transfer.success"
