# Implementation TODO

## Sprint 1: Safety and Foundations

## 1) Shared Paystack Client
- Create `payments/integrations/paystack/client.py`
- Add:
  - default timeout (e.g., 20s)
  - retry with backoff for 429/5xx/network errors
  - structured error mapping
- Replace direct `requests.post/get` in:
  - `files/sale_service.py`
  - `files/nightly_batch.py`
  - `files/reconcile.py`
  - `driver_api/services.py`

Acceptance:
- No raw provider HTTP calls outside the shared client.

## 2) Idempotency Infrastructure
- Add model `PaymentIdempotencyKey`:
  - `scope`, `key`, `actor_id`, `request_hash`, `response_snapshot`, timestamps
  - unique `(scope, key, actor_id)`
- Add middleware/helper to enforce idempotency for write endpoints.
- Apply to:
  - sale initialize
  - withdrawal request
  - refund request

Acceptance:
- Duplicate retried requests return same logical result without double writes.

## 3) Webhook Event Store and Dedup
- Expand webhook log model:
  - provider event id/hash, `processed`, `processed_at`, `error_reason`
- Add unique dedup key constraint.
- Update webhook handler:
  - persist event first
  - skip if already processed
  - mark success/failure outcome

Acceptance:
- Replayed webhook does not create duplicate ledger/payout effects.

## Sprint 2: Unified Withdrawal Flow

## 4) Unified Withdrawal Service
- Create `payments/payouts/services.py`:
  - `create_withdrawal_request(...)`
  - `evaluate_eligibility(...)`
  - `process_withdrawal_request(...)`
  - `mark_withdrawal_paid(...)`
  - `mark_withdrawal_failed(...)`
- Merge role checks from `files/withdrawal_service.py` and `driver_api/services.py`.
- Standardize statuses across both systems.

Acceptance:
- All withdrawal APIs call this single service path.

## 5) Ledger Event Standardization
- Ensure consistent event model:
  - hold on approval
  - debit + release on paid
  - release on fail/cancel
- Keep append-only writes.
- Add invariant checks:
  - no negative available balance after posting

Acceptance:
- End-to-end ledger trace from request to payout outcome.

## 6) Async Processing and Queues
- Route processing through Celery tasks:
  - `payouts.realtime`
  - `payouts.batch`
  - `webhooks.paystack`
- Add dead-letter handling for exhausted retries.

Acceptance:
- Synchronous API path only enqueues, does not block on provider calls.

## Sprint 3: Strategy, Reconcile, and Cutover

## 7) Payout Strategy Layer
- Add strategy enum to withdrawal:
  - `batch` or `realtime`
- Implement executors:
  - `execute_batch(date)`
  - `execute_realtime(withdrawal_id)`
- Reuse same completion/failure handlers.

Acceptance:
- Switching strategy does not change ledger correctness.

## 8) Reconciliation Expansion
- Extend reconcile command:
  - include realtime transfers
  - compare amount, recipient, final status
- Persist mismatch classes and severity.
- Add alert adapters:
  - email/slack/webhook

Acceptance:
- Daily reconciliation report includes batch + realtime.

## 9) Observability
- Add structured logs with:
  - `request_id`, `idempotency_key`, `withdrawal_id`, `sale_id`, `provider_ref`
- Add metrics:
  - payout success rate
  - webhook processing lag
  - retries/manual review counts

Acceptance:
- Team can trace any payout from API request to provider settlement.

## 10) Testing Plan
- Unit:
  - eligibility rules
  - idempotency behavior
  - webhook dedup
- Integration:
  - payout success/fail webhook transitions
  - refund + ledger reversal
  - batch transfer partial failures
- Load:
  - withdrawal spikes
  - webhook replay storms

Acceptance:
- Critical flows covered with deterministic tests and no flaky behavior.

## Cutover Checklist
1. Deploy behind feature flags.
2. Run dual-run reconciliation for 7 days.
3. Validate mismatch/error thresholds.
4. Flip traffic to unified endpoints.
5. Decommission old flow paths.
