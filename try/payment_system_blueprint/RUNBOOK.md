# Payments Runbook

## Scope
Operational procedures for:
- payout failures
- webhook backlog/replay
- reconciliation mismatches
- Paystack outages/degradation

## Severity Levels
- SEV-1: Broad payout blockage or ledger corruption risk
- SEV-2: Partial payout failures or sustained webhook lag
- SEV-3: Isolated user payout issues

## Core Dashboards/Signals
- Queue depth (`payouts.*`, `webhooks.paystack`)
- Webhook processing lag (received vs processed)
- Payout success/failure ratio
- Reconciliation mismatch count
- Manual review queue size

## Incident: Paystack API Outage
Symptoms:
- transfer/init calls timing out or 5xx spikes

Actions:
1. Enable circuit-breaker mode (pause realtime payouts).
2. Continue accepting withdrawal requests and posting HOLD entries.
3. Route all new payouts to `batch` strategy until recovery.
4. Increase retry backoff window for transient errors.
5. Post status update to support/admin channel.

Exit criteria:
- Error rates return to baseline for 30+ minutes.
- Controlled resume of realtime queue.

## Incident: Webhook Backlog
Symptoms:
- growing unprocessed webhook events
- delayed payout status updates

Actions:
1. Scale webhook workers horizontally.
2. Prioritize transfer events over low-priority event types.
3. Re-run failed events from persisted webhook store.
4. Verify dedup is active to prevent double posting.

Exit criteria:
- backlog drains to normal threshold.

## Incident: Reconciliation Mismatches
Symptoms:
- daily reconcile reports non-zero mismatches

Actions:
1. Classify mismatch:
   - amount
   - recipient
   - status divergence
2. Lock affected withdrawals from further retries.
3. Open manual review ticket with full trace:
   - withdrawal id
   - local ledger refs
   - provider refs
4. Perform corrective entry only via append-only ledger events.

Exit criteria:
- all mismatches resolved or explicitly approved exceptions.

## Incident: Duplicate Withdrawal Reports
Symptoms:
- user reports two payouts for one intent

Actions:
1. Check idempotency record by actor + key.
2. Check webhook replay logs and dedup keys.
3. Confirm whether duplicate provider transfer or local double-post.
4. If local double-post:
   - freeze affected account for withdrawal actions
   - post corrective reversal ledger entry
   - create root cause ticket

## Manual Review Queue Procedure
1. Query withdrawals where `needs_manual_review=true`.
2. For each item verify:
   - eligibility snapshot
   - API payload/response
   - webhook outcomes
3. Choose one:
   - retry payout
   - cancel and release hold
   - escalate to finance/compliance
4. Record resolution reason and operator id.

## Safe Reprocessing Rules
- Never delete ledger rows.
- Never mutate historical webhook payloads.
- Reprocessing must be idempotent and reference original event key.
- Corrective actions must be additive entries only.

## Operational Commands (Template)
- Trigger pending payout retry worker:
  - `python manage.py shell -c "<enqueue_pending_withdrawals>"`
- Trigger reconcile run:
  - `python manage.py reconcile`
- Trigger batch payout:
  - `python manage.py nightly_batch`

Note:
- Use feature flags to control strategy and cutover behavior.

## Post-Incident Review Template
1. Timeline (UTC)
2. Blast radius (users/amount)
3. Root cause
4. Detection gap
5. Immediate fix
6. Long-term preventive action
7. Owner and deadline
