# Unified Payment System Usage

## Keep
- `payments/integrations/paystack/client.py`
- `payments/idempotency.py`
- `payments/webhooks/paystack.py`
- `payments/payouts/services.py`
- `payments/payouts/tasks.py`
- `payments/reconciliation/service.py`
- `payments/observability/metrics.py`
- `driver_api/unified_bridge.py`
- `driver_api/tasks.py` webhook reconcile hook
- `driver_api/models.py` link field: `payment_withdrawal`

## Remove or Deprecate
- `files/withdrawal_service.py` (legacy duplicate logic, not used by current API flow)
- Legacy direct webhook/transfer logic outside `payments/webhooks/paystack.py`
- Any raw Paystack HTTP calls outside `payments/integrations/paystack/client.py`

## Keep for Compatibility (Temporary)
- `payments/services/withdrawal_service.py` (currently a passthrough wrapper to unified payouts service)
- `payments/urls.py` -> `files.urls` alias

## How to Use

### 1) User withdrawal flow (wallet)
Use `POST wallet/withdraw/` with headers:
- `Idempotency-Key: <unique-key>`
- `X-Request-ID: <trace-id>` (recommended)

Payload:
```json
{
  "amount_kobo": 120000,
  "strategy": "realtime"
}
```

Notes:
- `strategy` can be `realtime` or `batch`.
- Duplicate `Idempotency-Key` replays the same logical result.

### 2) Driver withdrawal flow
Use `POST withdrawals/` on driver API with header:
- `Idempotency-Key: <unique-key>`

Driver withdrawals are bridged into unified `payments.Withdrawal` through:
- `driver_api/unified_bridge.py`

### 3) Webhooks
Use one shared handler:
- `POST webhooks/paystack/` (general)
- `POST withdrawals/paystack/webhook/` (driver transfer-only path)

Requirements:
- Pass `X-Paystack-Signature`.
- Pass `X-Request-ID` (recommended for traceability).

Behavior:
- Event is stored first.
- Replay is deduplicated.
- Transfer events update `payments.Withdrawal`, then sync linked driver withdrawal.

### 4) Async workers
Core tasks:
- `payments.payouts.execute_realtime`
- `payments.payouts.execute_batch`
- `payments.payouts.process_withdrawal` (compat alias)
- `payments.payouts.retry_pending_withdrawals`
- `driver_api.process_withdrawal`
- `driver_api.retry_pending_withdrawals`

Run Celery worker/beat so API requests enqueue work instead of blocking.

### 5) Reconciliation
Run daily reconciliation from `payments/reconciliation/service.py` (or management command wrapper if you add one).

Expected output:
- checked count
- mismatch count
- mismatch severity classes

### 6) Observability
Structured logs now include:
- `request_id`
- `idempotency_key`
- `withdrawal_id`
- `provider_ref`

Metrics now include:
- `payments.payout.success_total`
- `payments.payout.failed_total`
- `payments.webhook.processing_lag_ms`
- `driver.withdrawal.retry_total`
- `driver.withdrawal.manual_review_total`

## Recommended Cleanup Sequence
1. Stop references to `files/withdrawal_service.py` in docs/readmes.
2. Keep compatibility wrappers for one release.
3. Remove wrappers once all callers use unified service modules directly.
4. Add missing DB migrations in `payments/migrations` if not yet generated/applied.
5. Run full test suite and dual-run reconciliation before hard cutover.
