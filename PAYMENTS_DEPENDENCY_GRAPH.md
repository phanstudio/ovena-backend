## Payments & Driver Payments Dependency Graph

This document maps out how **every payment‑related piece** of the system depends on the others – from HTTP entrypoints, through service layers, to Paystack and back via webhooks and reconciliation.

---

## 1. High‑level components

- **Core user domain**
  - `accounts.models.User`
  - `accounts.models.DriverProfile` / `DriverBankAccount`
- **Payments domain (`payments/`)**
  - `payments.models`:
    - `UserAccount` – per‑user payment profile (Paystack recipient + bank snapshot).
    - `Sale` – incoming payment (Paystack charge) with split snapshot.
    - `LedgerEntry` – immutable accounting entries.
    - `Withdrawal` – outgoing payout to a user.
    - `PaymentIdempotencyKey` – generic idempotency tracker.
    - `PaystackWebhookLog` – Paystack webhook storage + dedup.
    - `ReconciliationLog` – daily reconciliation summary.
  - `payments.integrations.paystack.client.PaystackClient` – wraps `paystackapi` SDK.
  - `payments.services.sale_service` – initialize sale, complete service, refund.
  - `payments.services.split_calculator` – compute splits + create ledger entries.
  - `payments.idempotency` – generic begin/save idempotency helpers.
  - `payments.payouts.services` – unified wallet/withdrawal engine.
  - `payments.payouts.tasks` – Celery workers for payouts (compat with `files.views`).
  - `payments.webhooks.paystack` – single Paystack webhook handler.
  - `payments.reconciliation.service` – daily reconciliation against Paystack.
  - `payments.views` – DRF API façade for wallet + sales + webhooks.
- **Driver API (`driver_api/`)**
  - `driver_api.models.DriverWithdrawalRequest` – driver‑side withdrawal record.
  - `driver_api.services` – driver wallet/ledger + withdrawal rules.
  - `driver_api.unified_bridge` – bridge `DriverWithdrawalRequest` → `payments.Withdrawal`.
  - `driver_api.tasks` – driver Celery tasks (process + retry + webhook reconcile).
  - `driver_api.views` – driver HTTP API, including driver webhook endpoint.
- **Ordering (`menu/`)**
  - `menu.payment_services` – initializes Paystack transactions using `PaystackClient`.
  - `menu.payment_views.paystack_webhook` – legacy order‑level webhook (for order status only).

---

## 2. Money IN: customer payments (sales)

### 2.1 Order → Paystack → `payments.Sale`

**Call chain** (initializing a checkout link for an order):

1. `menu.views.order.ResturantOrderView.accept_order`
   - Calls:
     - `menu.payment_services.initialize_paystack_transaction(total, email)`
2. `menu.payment_services.initialize_paystack_transaction`
   - Depends on:
     - `payments.integrations.paystack.client.PaystackClient.initialize_transaction(payload)`
   - Does:
     - Builds Paystack payload `{amount (kobo), email}`.
     - Returns Paystack SDK’s transaction init response (auth URL, reference, etc.).
3. (Planned / blueprint) For platform‑level sales:
   - `payments.views.initialize_sale_view` (DRF)
     - Enforces **idempotency** via `Idempotency-Key`:
       - `payments.idempotency.begin_idempotent_request(scope="sale_initialize", actor_id=user.id, key, payload)`
     - Calls:
       - `payments.services.sale_service.initialize_sale(...)`
     - Persists response via:
       - `payments.idempotency.save_idempotent_response(row, result)`
   - `payments.services.sale_service.initialize_sale`
     - Reads:
       - `payments.models.UserAccount` / `payments.models.PlatformConfig`
     - Calls:
       - `payments.services.split_calculator.load_split_config`
       - `payments.services.split_calculator.calculate_split`
       - `PaystackClient.initialize_transaction`
     - Writes:
       - `payments.models.Sale` with `split_snapshot` and `paystack_reference`.

**Why it’s wired this way**:

- `menu` uses `PaystackClient` so all Paystack calls go through one integration layer.
- The platform‑level `payments.views.initialize_sale_view` + `sale_service` own the canonical sale/ledger story (escrow + splits).

### 2.2 Paystack → webhook → `Sale` status/ledger

**Unified Paystack webhook**:

1. External:
   - Paystack sends `POST /api/webhooks/paystack/` (configured endpoint).

2. `payments.views.paystack_webhook_view`
   - Reads raw body + Paystack signature.
   - Delegates to:
     - `payments.webhooks.paystack.handle_paystack_webhook(...)`.

3. `payments.webhooks.paystack.handle_paystack_webhook`
   - Depends on:
     - `django.conf.settings.PAYSTACK_SECRET_KEY` for HMAC verification.
     - `payments.models.PaystackWebhookLog` for dedup and persistence.
     - `payments.webhooks.paystack.process_event` for actual business logic.
     - Metrics: `payments.observability.metrics.increment`, `observe_ms`.
   - Does:
     - `_load_body` → parse JSON.
     - `_event_keys` → extract `(event_type, ref, event_id, event_hash)`.
     - `_verify_signature` → HMAC check.
     - `PaystackWebhookLog.get_or_create(event_hash=...)` (dedup).
     - Skips reprocessing if already `processed=True`.
     - If invalid signature → increments invalid signature metrics and 400.
     - On success:
       - Calls `process_event(body)`.
       - Marks webhook log as processed.
       - Emits metrics (`received_total`, `processed_total`, error totals).

4. `payments.webhooks.paystack.process_event`
   - For `charge.success`:
     - Looks up `Sale` via `paystack_reference`.
     - Sets `sale.status = "in_escrow"`, saves.
   - For transfer events (`transfer.success` / `.failed` / `.reversed`):
     - Uses `_find_payment_withdrawal` to find `payments.models.Withdrawal` by `paystack_transfer_ref` or `paystack_transfer_code`.
     - Calls:
       - `mark_withdrawal_paid` **or** `mark_withdrawal_failed`.
       - `_sync_driver_withdrawal_from_linked_payment`:
         - imports `driver_api.services.mark_withdrawal_paid/failed`.
         - If driver withdrawal is linked (`payment_withdrawal.driver_withdrawal`), syncs driver record.
       - If no driver sync happened:
         - `_reconcile_driver_withdrawal`:
           - imports `driver_api.tasks.reconcile_paystack_webhook`.
           - Delegates to driver task which finds and updates `DriverWithdrawalRequest`.

**Legacy order webhook (`menu.payment_views.paystack_webhook`)**:

- Independent, order‑only webhook:
  - Verifies signature manually.
  - Updates `menu.models.Order` payment status (`confirmed`/`payment_pending` → `preparing`).
  - Logs `OrderEvent` and pushes websocket notifications.
- It does **not** touch the unified `payments.Sale`/`Withdrawal` ledger; it’s purely for restaurant order state.

---

## 3. Money OUT: unified wallet + withdrawals

### 3.1 Wallet balance + withdrawal request API (platform side)

**HTTP entrypoints**:

1. `payments.views.balance_view` – `GET /api/wallet/balance/`
   - Calls:
     - `payments.payouts.services.get_balance_summary(user_id)`
   - `get_balance_summary`:
     - Depends on:
       - `payments.services.split_calculator.get_ledger_balance(user)`
       - `_pending_total(user)` (pending `Withdrawal` rows).
     - Returns:
       - `total_balance_kobo`, `pending_withdrawal_kobo`, `available_balance_kobo`,
       - `minimum_withdrawal_kobo` (based on user role),
       - convenience NGN values and flags (`can_withdraw`, `needed_to_withdraw_kobo`).

2. `payments.views.request_withdrawal_view` – `POST /api/wallet/withdraw/`
   - Enforces **headers**:
     - `Idempotency-Key` (required).
     - `X-Request-ID` (optional, for tracing).
   - Calls:
     - `begin_idempotent_request(scope="withdrawal_request", actor_id=user.id, key, payload)`.
     - `create_withdrawal_request(user_id, amount_kobo, idempotency_key, strategy)`.
     - Optionally `payments.payouts.tasks.process_withdrawal.delay(...)` when `strategy == "realtime"`.
     - `save_idempotent_response(row, response_payload)`.
   - Returns:
     - `withdrawal_id`, `status`, `strategy`, message, etc.

**Core withdrawal service**:

3. `payments.payouts.services.create_withdrawal_request`
   - Inputs:
     - `user_id`, `amount_kobo`, `idempotency_key`, optional `strategy`, `request_id`.
   - Depends on:
     - `accounts.models.User` (via `User.objects.select_for_update()`).
     - `UserAccount` (for `paystack_recipient_code`).
     - `evaluate_eligibility(user, amount_kobo)`.
     - `payments.services.split_calculator._create_ledger_entry` (debit hold).
   - Flow:
     - Coerces strategy (`batch`/`realtime`).
     - If a `Withdrawal` with same `(user, idempotency_key)` exists → returns it (`created=False`).
     - Runs `evaluate_eligibility`:
       - Uses:
         - user role (`driver`, `business_owner`, `referral`),
         - ledger balance,
         - pending withdrawals,
         - platform limits (min amount, daily count/amount),
         - cooldown since last complete withdrawal,
         - presence of `UserAccount.paystack_recipient_code`.
       - Returns `WithdrawalDecision` (eligible + checks + thresholds).
     - On ineligible → logs warning and raises `ValueError`.
     - On eligible:
       - Creates a **hold ledger entry** (debit).
       - Creates `Withdrawal` with:
         - `status="pending_batch"`,
         - `strategy` (batch/realtime),
         - `idempotency_key`,
         - `paystack_recipient_code` from `UserAccount`,
         - link to the hold `LedgerEntry`.

4. `payments.payouts.services.execute_realtime`
   - Called by:
     - `payments.payouts.services.process_withdrawal_request` (legacy alias).
     - `driver_api.unified_bridge.process_driver_withdrawal_with_payments` (for driver payouts).
   - Does:
     - Transitions `Withdrawal.status` from `pending_batch` → `processing`.
     - Builds a Paystack transfer payload:
       - `source="balance"`, `amount=withdrawal.amount`, `recipient=withdrawal.paystack_recipient_code`, `reason="Withdrawal <id>"`.
     - Calls:
       - `PaystackClient.initiate_transfer(payload)`.
     - Stores:
       - `paystack_transfer_ref` and `paystack_transfer_code`.

5. `payments.payouts.services.execute_batch`
   - Used by:
     - Cron / management commands for nightly batch payouts.
   - Flow:
     - Selects `Withdrawal` rows with `status="pending_batch"` and `strategy="batch"`.
     - Marks them `processing`, sets `batch_date`, `processed_at`.
     - Builds a bulk transfer list and calls:
       - `PaystackClient.bulk_transfer({"currency": "NGN", "transfers": [...]})`.
     - Records returned `reference` / `transfer_code` on each withdrawal.

6. Final outcome transitions:
   - `payments.payouts.services.mark_withdrawal_paid`
     - Switches `status` → `complete`, sets `completed_at`.
     - Emits metrics: `payments.payout.success_total{strategy=...}`.
   - `payments.payouts.services.mark_withdrawal_failed`
     - Switches `status` → `failed`, sets `failure_reason`.
     - Creates a compensating `LedgerEntry` (credit) to release held funds.
     - Emits metrics: `payments.payout.failed_total{strategy=...}`.

---

## 4. Driver withdrawals → unified payments

### 4.1 Driver API flow

**Entrypoints**:

1. `driver_api.views.DriverWithdrawEligibilityView` – `GET /api/driver/withdrawals/eligibility/`
   - Calls:
     - `driver_api.services.evaluate_withdrawal_eligibility(driver)`.
   - Returns a summarized `WithdrawalDecision` in driver currency (Decimal instead of kobo).

2. `driver_api.views.DriverWithdrawListCreateView`:
   - `GET /api/driver/withdrawals/` – list `DriverWithdrawalRequest` for current driver.
   - `POST /api/driver/withdrawals/` – **driver withdrawal initiation**:
     - Requires `Idempotency-Key` header.
     - Validates payload via `WithdrawalRequestCreateSerializer`.
     - Calls:
       - `driver_api.services.create_withdrawal_request(driver, amount, idempotency_key)`.
     - If created and `status == APPROVED`:
       - Queues async processing:
         - `driver_api.tasks.process_withdrawal.delay(withdrawal.id)`.

3. `driver_api.tasks.process_withdrawal`
   - Looks up `DriverWithdrawalRequest`.
   - Calls:
     - `driver_api.services.process_withdrawal_request(withdrawal)`.

4. `driver_api.services.process_withdrawal_request`
   - Delegates **fully** to the unified payments engine:
     - `driver_api.unified_bridge.process_driver_withdrawal_with_payments(...)`
       - Passing:
         - `withdrawal`,
         - a Paystack recipient function (`_ensure_transfer_recipient`),
         - `MAX_RETRY_COUNT`.

### 4.2 Driver → payments bridge

- `driver_api.unified_bridge.process_driver_withdrawal_with_payments`
  - Preconditions:
    - `withdrawal.status == APPROVED`.
    - Driver has a verified `DriverBankAccount`.
  - Flow:
    1. Marks `DriverWithdrawalRequest.status` → `PROCESSING`, sets `processed_at`.
    2. Calls `ensure_recipient_fn(bank)` → Paystack transfer recipient code (via `PaystackClient.create_transfer_recipient`).
    3. Calls `_ensure_payments_withdrawal(withdrawal, recipient_code)`:
       - Tries to re‑attach existing `payments.Withdrawal` by:
         - direct FK (`payment_withdrawal_id`),
         - or stored ID in `review_snapshot`.
       - If none:
         - Ensures `UserAccount` exists for `withdrawal.driver.user` and updates its `paystack_recipient_code`.
         - Creates `payments.Withdrawal` with:
           - `user = driver.user`,
           - `amount = withdrawal.amount * 100` (kobo),
           - `status = "pending_batch"`,
           - `strategy = realtime`,
           - `idempotency_key = "driver:{driver_withdrawal.idempotency_key}"`,
           - `paystack_recipient_code = recipient_code`.
         - Links back to `DriverWithdrawalRequest.payment_withdrawal` and stores ID in `review_snapshot`.
    4. Calls:
       - `payments.payouts.services.execute_realtime(payment_withdrawal)`.
    5. Refreshes payment withdrawal, then:
       - Copies `paystack_transfer_ref` into `DriverWithdrawalRequest.transfer_ref` (with fallback if empty).
       - Adds `payment_withdrawal_id` and `payment_transfer_code` to `review_snapshot`.
    6. Handles errors:
       - Increments `retry_count`, emits `driver.withdrawal.retry_total`.
       - If retries exhausted:
         - `mark_failed` with `manual=True`, increments `driver.withdrawal.manual_review_total`.
       - If retries remain:
         - Resets status back to `APPROVED` to allow re‑queuing.

### 4.3 Driver reconciliation from Paystack events

**Primary path** – via payment linkage:

- When `payments.webhooks.paystack.process_event` sees a transfer event:
  - Finds `Withdrawal` (payments).
  - Calls `mark_withdrawal_paid` / `mark_withdrawal_failed`.
  - Then calls `_sync_driver_withdrawal_from_linked_payment`:
    - If `withdrawal.driver_withdrawal` exists:
      - Calls `driver_api.services.mark_withdrawal_paid` / `.mark_withdrawal_failed`.

**Fallback path** – via reference reconciliation:

- If there is no linked driver withdrawal:
  - `_reconcile_driver_withdrawal` calls `driver_api.tasks.reconcile_paystack_webhook(transfer_reference, transfer_status, reason)`.
- `driver_api.tasks.reconcile_paystack_webhook`:
  - Attempts to locate `DriverWithdrawalRequest` by:
    1. `payment_withdrawal__paystack_transfer_ref`,
    2. then `transfer_ref`,
    3. then `review_snapshot__payment_withdrawal_id`.
  - Applies:
    - `mark_withdrawal_paid` or `mark_withdrawal_failed(manual=False)`.

---

## 5. Reconciliation & monitoring

### 5.1 Daily reconciliation

- `payments.reconciliation.service.run_reconciliation(run_date, alert_callback=None)`
  - Uses:
    - `_collect_candidates(run_date)` to gather `Withdrawal` rows that:
      - are batch with `batch_date == run_date`, or
      - are realtime with `processed_at.date == run_date`,
      - and have a non‑empty `paystack_transfer_code`.
    - `PaystackClient.fetch_transfer(code)` for each candidate.
  - Compares for each:
    - `amount` vs `withdrawal.amount` (amount mismatch).
    - `recipient.recipient_code` vs `withdrawal.paystack_recipient_code` (recipient mismatch).
    - Provider status vs local status with `_local_vs_provider_status` (status mismatch).
  - On errors:
    - For exceptions when calling Paystack, records a `provider_fetch_error`.
  - Aggregates mismatches with a severity (`high`, `critical`, etc.).
  - Persists a `ReconciliationLog` with summary + mismatch details.
  - If mismatches and `alert_callback` is provided:
    - Calls `alert_callback(summary, mismatches)` so you can notify Slack, email, etc.

### 5.2 Metrics and observability

- **Payments metrics**
  - Payouts:
    - `payments.payout.success_total{strategy}` – in `mark_withdrawal_paid`.
    - `payments.payout.failed_total{strategy}` – in `mark_withdrawal_failed`.
  - Webhooks:
    - `payments.webhook.received_total{event}`.
    - `payments.webhook.processed_total{event}`.
    - `payments.webhook.replay_total{event}`.
    - `payments.webhook.invalid_signature_total{event}`.
    - `payments.webhook.error_total{event}`.
    - `payments.webhook.processing_lag_ms{event}` (histogram/summary).

- **Driver metrics**
  - `driver.withdrawal.retry_total` – each retry attempt from the driver unified bridge.
  - `driver.withdrawal.manual_review_total` – when automated processing gives up and flags a withdrawal.

These metrics are emitted from:

- `payments.payouts.services` (payout metrics).
- `payments.webhooks.paystack` (webhook metrics).
- `driver_api.unified_bridge` (driver‑side retry/manual metrics).

---

## 6. Summary: how everything hangs together

- **Entrypoints**:
  - Customers/clients hit:
    - `menu` views to initialize payments,
    - `payments` views for platform wallet operations,
    - `driver_api` views for driver wallet/withdrawals.
  - Paystack hits:
    - `payments.views.paystack_webhook_view` for unified sale/withdrawal events.
    - (Legacy) `menu.payment_views.paystack_webhook` for order status only.

- **Core engine**:
  - All **money state** (Sales, LedgerEntries, Withdrawals, Webhook logs, Reconciliation logs) lives in `payments.models`.
  - Paystack is only spoken to through `PaystackClient`, used by:
    - `sale_service.initialize_sale` / `process_refund`,
    - `payouts.services.execute_realtime` / `execute_batch`,
    - `reconciliation.service.run_reconciliation`.

- **Per‑role integration**:
  - Drivers:
    - Have their own `DriverWithdrawalRequest` entities, but all actual money movement is proxied into `payments.Withdrawal` via `driver_api.unified_bridge`.
  - Businesses/referrals:
    - Use `payments.Withdrawal` directly via the wallet API and payouts services.

- **Safety mechanisms**:
  - Idempotency:
    - `payments.idempotency` + `PaymentIdempotencyKey` for sales init and wallet withdrawals.
    - `DriverWithdrawListCreateView` requires `Idempotency-Key` for driver withdrawals.
  - Webhook dedup:
    - `PaystackWebhookLog` keyed by `event_hash` (and `event_id` where present).
  - Reconciliation:
    - `run_reconciliation` daily, with severity‑classified mismatches and optional alerting.
  - Metrics:
    - Payout results, webhook outcomes, and driver retry/manual flags all surface to monitoring.

This graph means you can reason about any payment‑related behaviour by following:

> **HTTP entrypoint → idempotency (if any) → domain service (`sale_service` / `payouts.services` / `driver_api.services`) → `PaystackClient` → webhook back in → `webhooks.paystack` → domain state updates → reconciliation (optional).**

