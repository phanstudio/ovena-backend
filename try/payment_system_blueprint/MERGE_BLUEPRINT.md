# Payment Systems Merge Blueprint

## Goal
Merge the strengths of:
- `files/` payments system (sales lifecycle, immutable ledger, reconciliation, batch payouts)
- `driver_api/` withdrawal system (idempotency, async processing, eligibility/risk controls)

Outcome: one unified payment platform with stronger reliability, auditability, and scale behavior.

## Target Architecture

### 1) Domains
- `payments/core`
  - Sale initialization
  - Escrow state transitions
  - Service completion and split posting
  - Refund orchestration
- `payments/ledger`
  - Immutable ledger entries
  - Balance projections and snapshots
  - Hash/tamper checks
- `payments/payouts`
  - Withdrawal request intake
  - Eligibility policy engine
  - Idempotent payout creation
  - Batch or real-time payout strategy
- `payments/integrations/paystack`
  - Transfer recipient management
  - Transfer and refund API calls
  - Webhook verification/parser
- `payments/reconciliation`
  - Daily transfer reconciliation jobs
  - Mismatch recording + alerting
- `payments/ops`
  - Cron/Celery schedules
  - Retry policy and dead-letter/manual review flows

### 2) State Model (Unified)
- Sale: `pending -> paid/in_escrow -> completed -> refunded/disputed`
- Withdrawal: `requested -> approved -> processing -> paid` or `failed` or `cancelled`
- Ledger events:
  - Credits for sale completion
  - Holds for withdrawal approval
  - Debits + hold releases on payout success
  - Hold releases on payout failure

### 3) Non-Negotiable Controls
- Request idempotency for mutation endpoints (header + DB unique constraint)
- Constant-time webhook signature checks (`hmac.compare_digest`)
- Atomic DB transitions for balance-affecting operations
- Persisted webhook event log with processing status and replay support
- Standard timeout/retry policy on all external API calls

## Data Model Merge Decisions

### Keep from `files/`
- Immutable ledger concept (`LedgerEntry` + hash verification)
- `PaystackWebhookLog` and `ReconciliationLog`
- Sales/refund domain (`Sale`)

### Keep from `driver_api`
- `idempotency_key` pattern + uniqueness constraint
- Eligibility snapshots and rule checks
- Celery-driven async payout handling
- Retry counters + manual review marker

### Introduce/Change
- Add `idempotency_key` to:
  - Sale initialization requests
  - Withdrawal requests (all user roles)
- Add webhook dedup keys:
  - Unique index on provider event id or payload hash
- Add payout strategy field:
  - `strategy = batch | realtime`
- Add processing timestamps:
  - `received_at`, `processed_at`, `acked_at` on webhook logs

## Processing Strategy

### Recommended hybrid
- Real-time payout for low volume/high urgency actors
- Nightly bulk payout for high-volume cohorts
- Both write through same withdrawal state machine and ledger rules

Why hybrid:
- Keeps cost/API call pressure under control (batch)
- Preserves good UX where speed matters (realtime)
- Avoids maintaining two different business rule engines

## Migration Plan (Phased)

### Phase 0: Safety Baseline
1. Add idempotency table/constraints before behavior changes.
2. Add webhook event persistence + dedup keying.
3. Normalize Paystack client with shared timeout/retry policy.
4. Add feature flags:
   - `PAYMENTS_UNIFIED_WITHDRAWAL_FLOW`
   - `PAYMENTS_PAYOUT_STRATEGY_DEFAULT`

### Phase 1: Unify Withdrawal Intake
1. Replace separate withdrawal create paths with one service entrypoint.
2. Apply eligibility checks as pluggable policies by role.
3. Always create hold ledger event on approval.
4. Queue async processing job.

### Phase 2: Unify Webhook Handling
1. Route all Paystack webhooks through one endpoint.
2. Verify signature with `compare_digest`.
3. Persist raw event before processing.
4. Process via idempotent dispatcher (event type + event id).

### Phase 3: Payout Execution Layer
1. Introduce payout executor interface:
   - `execute_realtime(withdrawal)`
   - `execute_batch(batch_id)`
2. Reuse same post-processing handlers:
   - success -> debit + release hold + mark paid
   - failure -> release hold + increment retry + manual review gate

### Phase 4: Reconciliation and Alerts
1. Extend reconcile job to include realtime payouts.
2. Add admin alerts for:
   - mismatches
   - max retries hit
   - orphaned webhook events

### Phase 5: Cutover and Decommission
1. Enable unified flow by feature flag in staging.
2. Run dual-write/dual-read validation window.
3. Switch production traffic.
4. Remove deprecated endpoints/services.

## Priority Fix List (Immediate)
1. Add idempotency to `files/` mutation endpoints.
2. Update `driver_api` webhook signature compare to constant-time.
3. Ensure all external requests have explicit timeout + retry policy.
4. Mark webhook logs as processed/failed with reason.
5. Add alert hooks for reconciliation failures and exhausted retries.

## Scale Behavior Design

### Database
- Indexes:
  - `(user/driver, status, created_at)` for withdrawals
  - `(paystack_reference/transfer_ref)` for webhook joins
  - `(source_type, source_id)` for ledger traceability
- Use `select_for_update` for balance-critical rows.
- Use append-only ledger writes; never in-place balance mutation as source of truth.

### Queue/Workers
- Separate queues:
  - `payouts.realtime`
  - `payouts.batch`
  - `webhooks.paystack`
- Dead-letter queue for repeated failures.
- Exponential backoff for transient provider errors.

### API/Provider
- Circuit-breaker behavior for Paystack outages.
- Idempotency keys for outbound transfer requests where supported.
- Rate limiting and jittered retries.

## Industry Standards Alignment Checklist

### Already close
- Atomic state transitions
- Ledger-style accounting
- Webhook signature verification
- Reconciliation job

### Gaps to close
- End-to-end idempotency everywhere
- Deterministic webhook dedup/replay controls
- Centralized observability (metrics + structured logs + alerts)
- Documented runbooks for payout incidents

## Definition of Done
- One webhook endpoint, one withdrawal service, one payout state machine.
- No duplicate withdrawals under retries/replays.
- Reconciliation mismatch rate near zero and alerting active.
- Manual review workflow for stuck/failing payouts.
- Load test passes for target peak volume with acceptable latency/SLA.

## Suggested Folder Follow-ups
- `payment_system_blueprint/IMPLEMENTATION_TODO.md`
- `payment_system_blueprint/SEQUENCE_DIAGRAMS.md`
- `payment_system_blueprint/RUNBOOK.md`
