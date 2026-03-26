## Payments & Driver API Test Suite Overview

This document explains the purpose of the **driver API** and **payments** tests in this project, how they fit into the unified payment system, and what risks each test guards against. All tests are written with `pytest`.

---

## Driver API tests (`driver_api/tests`)

These tests are about the **driver-facing API**, especially around withdrawals and how it integrates with the unified payments engine.

### 1. `test_driver_api.py`

**Goal**: High‑level API behaviour for driver endpoints (auth, profile, withdrawals, eligibility, background processing).

- **`test_non_driver_cannot_access_dashboard`**
  - **What**: Sends `GET /api/driver/dashboard/` as a user without a driver profile.
  - **Asserts**: Response is `403 Forbidden`.
  - **Why it matters**: Ensures driver‑only endpoints are not exposed to regular users. This is both a security and correctness guarantee, especially important when those endpoints expose earnings and withdrawal information.

- **`test_driver_profile_endpoint`**
  - **What**: Creates a `DriverProfile` and calls `GET /api/driver/profile/`.
  - **Asserts**: Response is `200 OK` and the JSON `data.first_name` matches the profile.
  - **Why**: Confirms that the profile view correctly reads from the driver profile and that driver apps will see up‑to‑date data.

- **`test_withdrawal_idempotency_key_returns_existing_record`**
  - **What**:
    - Seeds a driver with a verified bank account and a credited ledger entry.
    - Calls `POST /api/driver/withdrawals/` twice with the **same** `Idempotency-Key` and amount.
  - **Asserts**:
    - First call returns `201 Created`, second returns `200 OK`.
    - Both responses reference the **same** withdrawal ID.
  - **Why**: Protects against double payouts when apps retry the request (e.g. due to network issues or user double‑tapping). Idempotency is critical when money is leaving the system.

- **`test_withdrawal_missing_idempotency_key_is_rejected`**
  - **What**: Calls `POST /api/driver/withdrawals/` without the `Idempotency-Key` header.
  - **Asserts**: API responds with `400 Bad Request` and a message mentioning the missing header.
  - **Why**: Enforces a strict contract that every withdrawal must be idempotent. This prevents future callers from accidentally building unsafe flows.

- **`test_withdrawal_eligibility_endpoint_exposes_decision_snapshot`**
  - **What**:
    - Monkeypatches `driver_api.views.evaluate_withdrawal_eligibility` to return a fake decision object (eligible + some limits).
    - Calls `GET /api/driver/withdrawals/eligibility/`.
  - **Asserts**:
    - Response `data` mirrors the decision (`eligible`, `minimum_amount`, `max_amount`, `available_balance`, `checks`).
  - **Why**: Guarantees that the mobile app can show **why** a driver can or cannot withdraw (bank verification, limits, cooldown, etc.), using the same data the engine uses internally.

- **`test_withdrawal_creation_triggers_background_processing_for_approved_request`**
  - **What**:
    - Monkeypatches `create_withdrawal_request` to:
      - Return a `DriverWithdrawalRequest` in `APPROVED` status.
      - Records the arguments passed.
    - Monkeypatches `process_withdrawal.delay` to record calls instead of hitting Celery.
    - Calls `POST /api/driver/withdrawals/` with a valid `Idempotency-Key`.
  - **Asserts**:
    - Response is `201 Created`.
    - `process_withdrawal.delay` is called exactly once with the new withdrawal ID.
  - **Why**: Verifies that the API enqueues withdrawal processing in the background instead of blocking the HTTP request or executing Paystack calls inline. This is crucial for performance and reliability under load.

---

### 2. `test_driver_phase5_unified_engine.py`

**Goal**: Ensure the **driver service layer** is correctly wired into the unified payments engine.

- **`test_process_withdrawal_request_delegates_to_unified_bridge`**
  - **What**:
    - Monkeypatches `driver_api.services.process_driver_withdrawal_with_payments` to capture arguments and return a sentinel object.
    - Calls `driver_api.services.process_withdrawal_request(...)` with a dummy withdrawal object.
  - **Asserts**:
    - The return value is the sentinel (so the call is truly delegated).
    - The same withdrawal object is passed through.
    - `ensure_recipient_fn` is callable.
    - `max_retry_count` equals `services.MAX_RETRY_COUNT`.
  - **Why**: This confirms that there is **one single path** from driver withdrawals into the core payments engine (`unified_bridge`), with the right hooks for Paystack recipient creation and retry behaviour. This is a critical part of the “all in one” design you want.

---

### 3. `test_driver_phase6_metrics.py`

**Goal**: Validate the **driver‑side reconciliation/withdrawal engine** implements safe failover and correct metrics.

- **`test_unified_bridge_increments_manual_review_metric_for_unverified_bank`**
  - **What**:
    - Builds a stub withdrawal with status `APPROVED` but a driver bank account that is **not verified**.
    - Monkeypatches `increment` to record metric calls.
    - Calls `process_driver_withdrawal_with_payments(...)`.
  - **Asserts**:
    - The withdrawal’s `mark_failed` is called with `"Driver bank account is not verified"` and `manual=True`.
    - At least one metric call is made to `"driver.withdrawal.manual_review_total"`.
  - **Why**: Ensures that if a driver’s bank account is not verified, payouts are **blocked**, marked for manual review, and that this is visible in monitoring. This is important for fraud/risk and compliance.

- **`test_unified_bridge_increments_retry_and_manual_on_exhausted_retries`**
  - **What**:
    - Builds a stub withdrawal with:
      - status `APPROVED`,
      - `retry_count = 2`,
      - a verified bank account.
    - Forces `ensure_recipient_fn` to raise an error (simulating Paystack or network failure).
    - Monkeypatches `increment` to capture metrics.
    - Calls `process_driver_withdrawal_with_payments(...)` with `max_retry_count=3`.
  - **Asserts**:
    - Withdrawal is marked failed with the error message (`"boom"`) and `manual=True` (since retries are exhausted).
    - Metrics include both `"driver.withdrawal.retry_total"` and `"driver.withdrawal.manual_review_total"`.
  - **Why**: Validates the **retry and escalation policy**: temporary issues can be retried automatically, but after enough failures the system gives up and flags the withdrawal for manual intervention, with metrics to alert the team.

---

### 4. `test_driver_webhook_unification.py`

**Goal**: Prove that driver withdrawals use the **shared Paystack webhook handling** from the payments app, and that fallback reconciliation is wired correctly.

- **`test_driver_webhook_delegates_to_shared_dispatcher`**
  - **What**:
    - Monkeypatches `driver_api.views.handle_paystack_webhook` to capture arguments and return `(200, "Webhook processed")`.
    - Sends a fake Paystack webhook to `POST /api/driver/withdrawals/paystack/webhook/`.
  - **Asserts**:
    - Response is `200` with `"Webhook processed"`.
    - `transfer_only` flag is `True`.
    - Signature and `X-Request-ID` headers are passed through.
  - **Why**: Confirms the driver webhook endpoint is a **thin proxy** to the unified payments webhook dispatcher, not a custom code path. This reduces duplicate logic and ensures consistent handling of Paystack events.

- **`test_reconcile_webhook_prefers_linked_payment_withdrawal_lookup`**
  - **What**:
    - Stubs `DriverWithdrawalRequest.objects` to capture filter calls and always return a stub withdrawal.
    - Monkeypatches `driver_api.tasks.mark_withdrawal_paid` to capture the withdrawal passed in.
    - Calls `driver_api.tasks.reconcile_paystack_webhook("trf-123", "success")`.
  - **Asserts**:
    - Filter is called with `{"payment_withdrawal__paystack_transfer_ref": "trf-123"}`.
    - Result and the withdrawal passed to `mark_withdrawal_paid` are the same stub.
  - **Why**: Ensures that when the payments side cannot sync the driver withdrawal directly, the fallback reconciliation task can still find and update the right driver withdrawal using the Paystack transfer reference. This is a safety net for data consistency across apps.

---

## Payments tests (`payments/tests`)

These tests are organized in **phases** that match the rollout of the unified payments system: idempotency/webhooks → unified withdrawals → payout executors → reconciliation.

### 1. `test_phase1_idempotency_webhooks.py`

**Goal**: Idempotency and webhook behaviour for **incoming money** (sales) and Paystack event handling.

- **`test_idempotent_request_replay_returns_saved_response`**
  - **What**:
    - Monkeypatches `payments.views.initialize_sale` so we can count how many times it’s called.
    - Sends two identical `POST /api/sales/initialize/` requests with the same `HTTP_IDEMPOTENCY_KEY`.
  - **Asserts**:
    - First call returns `201 Created`, second returns `200 OK`.
    - Response bodies are identical.
    - Underlying initializer is called **only once**.
    - Exactly one `PaymentIdempotencyKey` row is created.
  - **Why**: Guarantees that clients can safely retry sale initialization without double‑charging or creating multiple Sale records.

- **`test_idempotency_conflict_on_payload_mismatch`**
  - **What**:
    - Sends two `POST /api/sales/initialize/` requests with the **same idempotency key** but different payloads (different amounts).
  - **Asserts**:
    - First call `201`, second call `409 Conflict`.
    - Error message clearly states the payload is different.
  - **Why**: Prevents subtle bugs where a client might re‑use an idempotency key with a changed body, which could otherwise lead to ambiguous or incorrect behaviour.

- **`test_webhook_replay_dedup`**
  - **What**:
    - Creates a fake `charge.success` webhook payload.
    - Signs it using HMAC with `PAYSTACK_SECRET_KEY`.
    - Posts the same payload twice to `POST /api/webhooks/paystack/`.
  - **Asserts**:
    - Handler `process_event` is called exactly once.
    - Only one `PaystackWebhookLog` row is created and it’s marked `processed=True`.
  - **Why**: Paystack may retry webhooks. This ensures your system processes each **logical event once** while still logging and safely ignoring duplicates.

- **`test_webhook_processed_and_error_transitions`**
  - **What**:
    - Forces `process_event` to raise an error on first attempt.
    - Sends the same webhook again after switching `process_event` to succeed.
  - **Asserts**:
    - After the first attempt, the log is not processed and `error_reason` contains the error.
    - After the second attempt, the same log is marked processed, `processed_at` set, and `error_reason` cleared.
  - **Why**: Ensures webhook logs capture transient failures, but also recover and mark events as processed after a successful replay.

- **`test_transfer_event_syncs_driver_via_link_and_skips_fallback_reconcile`**
  - **What**:
    - Pretends a Paystack transfer event is received.
    - Mocks `_find_payment_withdrawal` to return a payment withdrawal and `_sync_driver_withdrawal_from_linked_payment` to return `True`.
  - **Asserts**:
    - `mark_withdrawal_paid` is called exactly once.
    - `_sync_driver_withdrawal_from_linked_payment` is called exactly once.
    - Fallback `_reconcile_driver_withdrawal` is **not** called.
  - **Why**: Verifies the **happy path** where all updates flow via the explicit FK between payment withdrawals and driver withdrawals, without needing fallback reconciliation.

- **`test_transfer_event_falls_back_to_reconcile_when_link_sync_not_available`**
  - **What**:
    - Simulates a `transfer.failed` event where `_sync_driver_withdrawal_from_linked_payment` returns `False`.
  - **Asserts**:
    - `mark_withdrawal_failed` is called with the Paystack failure reason.
    - `_reconcile_driver_withdrawal` is called with `transfer_reference`, `transfer_status="failed"`, and the reason.
  - **Why**: Ensures that even if the direct link to a driver withdrawal is missing, the system still knows how to reconcile and surface the failure at the driver level.

- **`test_webhook_lag_metric_is_recorded`**
  - **What**:
    - Sends a `transfer.success` event with a known event timestamp.
    - Observes metric calls by monkeypatching `observe_ms`.
  - **Asserts**:
    - At least one call to `payments.webhook.processing_lag_ms`.
    - Metric has non‑negative value and is tagged with the event type.
  - **Why**: Provides a way to monitor the delay between Paystack sending an event and your system processing it, which is important for payout SLAs and incident detection.

---

### 2. `test_phase2_unified_withdrawals.py`

**Goal**: Assert that **all withdrawals** (drivers, business, referral) go through a unified payouts service, with idempotency and wallet API behaviour verified.

- **`test_create_withdrawal_request_unified_service`**
  - **What**:
    - Sets `LEDGER_HASH_SALT` for deterministic hashes.
    - Creates a `User` with role `driver` and a corresponding `UserAccount` with a Paystack recipient code.
    - Adds a credit ledger entry via `_create_ledger_entry`.
    - Calls `payout_services.create_withdrawal_request(...)`.
  - **Asserts**:
    - Withdrawal is created (`created=True`), status `pending_batch`, amount matches, and a `ledger_entry` exists.
  - **Why**: Ensures the core engine for withdrawals:
    - debits the ledger via a hold entry,
    - enforces invariants,
    - and does **not** call Paystack directly from higher‑level code.

- **`test_create_withdrawal_request_idempotent`**
  - **What**:
    - Similar setup as above but calls `create_withdrawal_request` twice with the same user + idempotency key.
  - **Asserts**:
    - First call returns `created=True`, second `created=False`.
    - Both withdrawals share the same ID.
  - **Why**: Protects the core payouts service from double‑initiating the same withdrawal, no matter how many times the API or other code calls it.

- **`test_request_withdrawal_view_uses_unified_service_and_can_queue_realtime`**
  - **What**:
    - Seeds a driver user + `UserAccount` + credit ledger entry.
    - Monkeypatches `files.views.process_withdrawal.delay` to track calls.
    - Sends `POST /api/wallet/withdraw/` with `strategy="realtime"` and an idempotency key.
  - **Asserts**:
    - Response code `201`.
    - Strategy in response is `"realtime"`.
    - Exactly one background job is queued.
    - `PaymentIdempotencyKey` exists for this user/key/scope.
    - Exactly one `Withdrawal` exists for the user.
  - **Why**: Confirms the **public wallet API** is wired into:
    - the unified payouts service,
    - idempotency tracking, and
    - Celery‑based execution for realtime withdrawals.

- **`test_request_withdrawal_view_forwards_request_id_to_service`**
  - **What**:
    - Monkeypatches `files.views.create_withdrawal_request` to capture arguments, then calls `request_withdrawal_view` with `X-Request-ID`.
  - **Asserts**:
    - Service receives the same `request_id` and `idempotency_key` that were sent in headers.
  - **Why**: Ensures traceability across layers: a given `request_id` from the gateway can be followed into logs at the service level.

---

### 3. `test_phase3_payout_executors.py`

**Goal**: Test the **execution phase** of payouts (how money actually leaves via Paystack), both realtime and batch.

- **`test_create_withdrawal_persists_strategy`**
  - **What**:
    - Creates a driver user + `UserAccount` + ledger credit.
    - Calls `create_withdrawal_request(..., strategy="realtime")`.
  - **Asserts**:
    - Withdrawal is created and its `strategy` is `STRATEGY_REALTIME`.
  - **Why**: Makes sure the high‑level choice (batch vs realtime) is stored and available to later stages (batch job vs realtime executor).

- **`test_execute_realtime_sets_transfer_refs`**
  - **What**:
    - Similar setup + `UserAccount`.
    - Monkeypatches `paystack_client.initiate_transfer` to return fake reference and transfer code.
    - Calls `execute_realtime(withdrawal)`.
  - **Asserts**:
    - Status becomes `processing`.
    - `paystack_transfer_ref` and `paystack_transfer_code` are saved in the DB.
  - **Why**: Ensures realtime payouts:
    - correctly call Paystack via the integration client, and
    - persist all necessary provider identifiers for reconciliation and webhooks.

- **`test_execute_batch_processes_only_batch_strategy`**
  - **What**:
    - Seeds:
      - One batch withdrawal.
      - One realtime withdrawal.
    - Monkeypatches `paystack_client.bulk_transfer` to emulate Paystack response.
    - Calls `execute_batch()`.
  - **Asserts**:
    - Result `count == 1`.
    - Batch withdrawal status is `processing` with a `BULK_` transfer code.
    - Realtime withdrawal remains `pending_batch` with empty transfer code.
  - **Why**: Verifies the batch executor:
    - only touches `strategy=batch` withdrawals,
    - does not accidentally process realtime ones.
    - This prevents double payouts or mis‑routing of funds.

- **`test_mark_withdrawal_paid_and_failed_emit_metrics`**
  - **What**:
    - Creates a realtime withdrawal.
    - Monkeypatches `increment` to capture metric calls.
    - Calls `mark_withdrawal_paid` then `mark_withdrawal_failed`.
  - **Asserts**:
    - Metrics include:
      - `payments.payout.success_total` with `{"strategy": "realtime"}`,
      - `payments.payout.failed_total` with `{"strategy": "realtime"}`.
  - **Why**: Ensures core payout status transitions are visible via metrics, allowing alerting on increased failure rates.

---

### 4. `test_phase4_reconciliation.py`

**Goal**: Validate **daily reconciliation** between your local `Withdrawal` records and Paystack’s transfer history.

- **`test_reconcile_includes_batch_and_realtime`**
  - **What**:
    - Creates one batch and one realtime withdrawal for the previous day.
    - Fakes a `PaystackClient` whose `fetch_transfer` returns matching records.
    - Calls `run_reconciliation(run_date=...)`.
  - **Asserts**:
    - Summary shows `checked == 2` and `mismatches == 0`.
  - **Why**: Baseline guarantee that reconciliation:
    - inspects both strategies,
    - and does not flag false positives when everything matches Paystack.

- **`test_reconcile_classifies_severity_and_triggers_alert`**
  - **What**:
    - Creates a batch withdrawal with local values.
    - Fakes `PaystackClient.fetch_transfer` to return a conflicting record (different amount, status, recipient).
    - Calls `run_reconciliation(..., alert_callback=fake_alert)`.
  - **Asserts**:
    - Summary reports at least one mismatch.
    - `alert_callback` is invoked.
    - At least one mismatch is tagged with severity `"critical"` or `"high"`.
  - **Why**: Ensures the reconciliation engine:
    - detects significant money mismatches,
    - escalates them via an alert hook, and
    - classifies them so operations know which issues to prioritize.

---

## How this all fits your “all‑in‑one” payment system

- **Driver → Payments path is covered end‑to‑end**:
  - Driver API endpoints validate auth, enforce idempotency, and enqueue payouts (`driver_api/tests`).
  - The bridge and engine tests ensure driver withdrawals go through the **unified payments engine**, not ad‑hoc Paystack calls.
  - Webhook unification tests guarantee that Paystack events are processed once, update both payments and driver state, and fall back to reconciliation when needed.

- **Payments core is protected across phases**:
  - Phase 1: Idempotency and webhook behaviour for incoming money and Paystack events.
  - Phase 2: Unified withdrawals, wallet API, and idempotency on the way out.
  - Phase 3: Payout executor correctness for both realtime and batch, plus metrics.
  - Phase 4: Daily reconciliation between your ledger and Paystack, with proper alerting on mismatches.

Taken together, these tests act as a **safety net** for all flows that touch money: how it enters (sales), is held (ledger), leaves (withdrawals/payouts), reacts to provider events (webhooks), and is double‑checked later (reconciliation). They also encode the contracts you care about most: **idempotency, single source of truth, and observability**.

