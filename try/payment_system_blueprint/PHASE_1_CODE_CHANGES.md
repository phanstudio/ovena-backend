# Phase 1 Code Changes

## Scope
Phase 1 covers:
1. Shared Paystack client
2. Idempotency for write endpoints
3. Webhook dedup + processing state
4. Signature compare hardening
5. Baseline retries/timeouts

This document maps each item to exact current files and recommended new files.

## 1) Shared Paystack Client

## New files
- `payments/integrations/paystack/client.py`
- `payments/integrations/paystack/errors.py`

## Implement
- `PaystackClient` methods:
  - `initialize_transaction(payload)`
  - `refund(payload)`
  - `create_transfer_recipient(payload)`
  - `initiate_transfer(payload)`
  - `bulk_transfer(payload)`
  - `fetch_transfer(transfer_code)`
- Enforce:
  - default timeout (20s)
  - retry for transient failures (429, 5xx, network)
  - normalized exceptions

## Replace direct HTTP calls in existing files
- `files/sale_service.py`
  - replace `requests.post(.../transaction/initialize)` in `initialize_sale`
  - replace `requests.post(.../refund)` in `process_refund`
- `files/nightly_batch.py`
  - replace `requests.post(.../transfer/bulk)` in `_send_bulk_transfer`
- `files/reconcile.py`
  - replace `requests.get(.../transfer/{code})`
- `driver_api/services.py`
  - replace `requests.post(.../transferrecipient)` in `_ensure_transfer_recipient`
  - replace `requests.post(.../transfer)` in `_initiate_transfer`

## 2) Idempotency Foundation

## New files
- `payments/models/idempotency.py` (or add to existing `payments/models.py`)
- `payments/services/idempotency_service.py`
- migration file: `payments/migrations/xxxx_payment_idempotency.py`

## Model recommendation
- `PaymentIdempotencyKey`
  - `scope` (`sale_initialize`, `withdrawal_request`, `refund_request`)
  - `actor_id` (UUID/int/string)
  - `key` (header value)
  - `request_hash`
  - `response_snapshot` (JSON)
  - timestamps
  - unique constraint on `(scope, actor_id, key)`

## Endpoint-level changes
- `files/views.py`
  - `initialize_sale_view`:
    - require `Idempotency-Key`
    - hash request payload
    - return stored response on duplicate key
  - `request_withdrawal_view`:
    - require `Idempotency-Key`
    - same dedup behavior
  - `refund_sale_view`:
    - require `Idempotency-Key`

- `driver_api/views.py`
  - already requires `Idempotency-Key` for withdrawals
  - preserve existing behavior
  - migrate to shared idempotency service for consistency

## Service changes
- `files/sale_service.py`
  - wrap `initialize_sale` and `process_refund` entry with shared idempotency helper
- `files/withdrawal_service.py`
  - add `idempotency_key` param to `request_withdrawal`
  - enforce uniqueness per user and key

## 3) Webhook Event Store + Dedup

## Existing file updates
- `files/models.py` (`PaystackWebhookLog`)
  - add fields:
    - `event_id` (nullable, indexed)
    - `event_hash` (indexed)
    - `processed_at` (nullable datetime)
    - `error_reason` (blank text)
  - add unique constraint for dedup key:
    - preferred: `(event_id)` when present
    - fallback: `(event_type, event_hash)`

- migration file:
  - `payments/migrations/xxxx_webhook_dedup_fields.py`

## Webhook handler changes
- `files/views.py` in `paystack_webhook_view`:
  - parse event id from payload if available
  - compute `event_hash` from raw body
  - upsert/insert dedup record before processing
  - if duplicate and already processed: return `200` no-op
  - on success:
    - set `processed=True`, `processed_at=now`
  - on failure:
    - set `processed=False`, `error_reason=<exception>`

## Optional unification hook (now or phase 2)
- route `driver_api/views.py::PaystackWithdrawalWebhookView` to shared webhook processor.

## 4) Signature Compare Hardening

## File updates
- `driver_api/views.py`
  - in `PaystackWithdrawalWebhookView.post` replace:
    - `signature != expected`
  - with:
    - `hmac.compare_digest(signature, expected)`

No behavior change intended; only security hardening.

## 5) Timeout/Retry Baseline

## File updates (if shared client is not complete yet)
- add explicit timeout to all direct `requests.*` calls that remain.
- minimum in:
  - `files/sale_service.py`
  - `files/nightly_batch.py`
  - `files/reconcile.py`

Target:
- remove all ad-hoc timeout values after shared client adoption.

## 6) Concrete Function-by-Function Edit List

## `files/views.py`
- `initialize_sale_view`:
  - enforce idempotency header
  - call idempotency service before `initialize_sale`
- `refund_sale_view`:
  - enforce idempotency header
- `request_withdrawal_view`:
  - enforce idempotency header and pass to service
- `paystack_webhook_view`:
  - dedup insert/check
  - processed/error state persistence

## `files/withdrawal_service.py`
- `request_withdrawal(user_id, amount_kobo, idempotency_key)`
  - check for existing request by idempotency key and user
  - return prior result if duplicate

## `files/sale_service.py`
- `initialize_sale(...)`
  - use shared Paystack client
- `process_refund(...)`
  - use shared Paystack client

## `files/nightly_batch.py`
- `_send_bulk_transfer(...)`
  - use shared Paystack client
  - preserve rollback behavior

## `files/reconcile.py`
- transfer fetch path via shared client

## `driver_api/services.py`
- replace `_ensure_transfer_recipient` and `_initiate_transfer`
  - with shared client calls

## `driver_api/views.py`
- constant-time signature compare

## 7) Test Cases to Add in Phase 1

## Idempotency
- duplicate sale initialization returns same response and does not create second sale
- duplicate refund request does not create second refund action
- duplicate withdrawal request in `files/` returns same withdrawal id

## Webhooks
- duplicate webhook payload processed once only
- invalid signature rejected
- processing exception marks webhook log with `error_reason`

## Security/HTTP
- signature compare path passes for valid signature and fails for invalid
- provider timeout triggers retry logic (shared client unit test)

## 8) Suggested Order of Work
1. Add shared Paystack client + tests.
2. Patch all direct provider calls to use client.
3. Add idempotency model/service + wire endpoints.
4. Add webhook dedup migration and handler updates.
5. Patch `driver_api` signature compare.
6. Run full regression for sale/withdraw/refund/webhook flows.
