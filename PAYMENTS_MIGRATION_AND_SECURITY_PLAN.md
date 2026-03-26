## 1. Provider accounts – what and when

### 1.1 Concept

- **Provider account** (in this context) = representation of a **Paystack merchant environment** inside your app.
- Today you effectively have **one provider account**:
  - One Paystack secret key in `settings.PAYSTACK_SECRET_KEY`.
  - All transactions and transfers are made on behalf of that single merchant.
- A more advanced design would add a model like:

```python
class ProviderAccount(models.Model):
    """
    Represents a Paystack (or other PSP) merchant account
    that we can talk to with a specific secret key/config.
    """
    name = models.CharField(max_length=100)
    provider = models.CharField(max_length=30, default="paystack")
    secret_key = models.CharField(max_length=255)  # stored securely
    public_key = models.CharField(max_length=255, blank=True)
    environment = models.CharField(max_length=20, choices=[("live", "Live"), ("test", "Test")])
    is_default = models.BooleanField(default=False)
```

Then entities like `Sale` and `Withdrawal` could point at a specific `ProviderAccount`:

```python
provider_account = models.ForeignKey(ProviderAccount, on_delete=models.PROTECT)
```

This is useful when:

- You run **white‑label** or multi‑tenant payments for many separate merchants.
- Different businesses need completely separate Paystack accounts for compliance or settlement reasons.

You **don’t** need this complexity yet because:

- You’re operating one brand/platform.
- You already encode “who should receive what” in your **own ledger and splits**, and Paystack just sees “platform → many recipients”.

---

## 2. Paystack as source of truth – data access limits

### 2.1 What Paystack exposes

Paystack’s API (for one merchant account) gives you:

- **Charges / Transactions**:
  - List and filter by:
    - date ranges,
    - status,
    - customer/email,
    - reference.
- **Transfers**:
  - List transfers, filter by date, status, recipient, or reference.
- **Customers**:
  - List customers by email, etc.

It does **not** natively know your internal `user_id` / `driver_id` – you have to:

- Put those IDs inside **metadata** on charges/transfers, and/or
- Maintain your own mapping from `user_id` → `recipient_code`, `transfer_code`, `transaction_reference`.

### 2.2 Per-user queries

You asked:

> “does it allow us to filter what we need like all transactions related to a user?”

Answer:

- Directly: **no** – Paystack only sees “customers” and “recipients”, not your `accounts.User`.
- Practically:
  - You decide how to map your concept of “user” to Paystack:
    - **Option A**: Use `customer.email` as the join key (for incoming payments).
    - **Option B**: Use `transfer_recipient` as the join key (for payouts).
    - **Option C**: Put `user_id` / `driver_id` in the `metadata` of charges/transfers.
  - Then you:
    - Filter transfers by recipient or date at Paystack’s side.
    - Resolve to a **user** using your own DB.

So Paystack is a **second source of truth** (provider‑level truth), while **your DB is the primary source** for mapping provider data back to users and orders.

### 2.3 Rate limits and volume

- Paystack enforces API rate limits (usually sufficient for daily reconciliation and occasional on‑demand fetches).
- For **reconciliation**:
  - You’re already doing the right thing: fetch per transfer code that you know about (`run_reconciliation`).
  - This scales well: you don’t call “all transfers” at once; you look up only withdrawals that changed locally for a given date.

---

## 3. Roles – legacy vs new system

You mentioned:

> “on one end we are using the old role system, also roles have been revamped and mostly are a deprecated system because of multiple role accounts.”

Where roles are used now:

- `accounts.User.role` (current main auth model) controls:
  - app‑level roles (`customer`, `driver`, `businessadmin`, etc.).
- `payments.payouts.services` reads `user.role` to:
  - decide minimum withdrawal amounts per role,
  - choose which split/limits apply.

The fact that roles are being **revamped** means:

- You might end up representing roles as:
  - Many‑to‑many between `User` and `Role` models, plus
  - Derived roles via `profile_bases`.
- For payments you still only need **“payout role”**:
  - Is this payout “driver earnings”, “business earnings”, or “referral earnings”?

Migration path:

- Introduce a simple helper on `User` (or a separate field) that returns a **normalized payout role**:

```python
def get_payout_role(user: User) -> str:
    # Map complex/multi roles into a single payout role string
    if user.has_role("driver"):
        return "driver"
    if user.has_role("businessadmin"):
        return "business_owner"
    if user.has_role("referral"):
        return "referral"
    return "platform"
```

- Then in `payments.payouts.services` use `get_payout_role(user)` instead of relying directly on `user.role`.
- This allows your **auth/role system to evolve** without breaking the withdrawal logic; only this mapping needs updates.

---

## 4. Why `Order` has a payment reference vs `Sale`

> “for the sales talk why does order have payment references? why not attach to a sales object, or does that cause issues in the long run or am I still thinking of sale objects wrongly?”

### 4.1 Current setup

- `menu.models.Order` has:
  - `payment_reference` – the Paystack transaction reference for that specific order.
- `payments.models.Sale` has:
  - `reference` – internal sale reference.
  - `paystack_reference` – Paystack’s transaction reference.

So you currently have **two ways** to find the Paystack transaction for an order:

1. Directly, via `Order.payment_reference` → Paystack.
2. Indirectly, via `Sale.paystack_reference` once `Order` is associated with `Sale`.

### 4.2 Ideal relationship

Conceptually:

- `Order` = “this basket of food and logistics”.
- `Sale` = “this flow of money that pays for something (possibly an order)”.

The cleanest model is:

- `Order` **optionally links to** `Sale`:

```python
class Order(models.Model):
    ...
    sale = models.ForeignKey("payments.Sale", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    ...
```

- `Sale` is the **only object** that holds:
  - `paystack_reference`,
  - `split_snapshot`,
  - total amount.
- The legacy `Order.payment_reference` then becomes:
  - either a compatibility field (eventually deprecated), or
  - a trivial mirror of `order.sale.paystack_reference`.

**Why the current design happened:**

- The order system existed long before the unified `Sale`/ledger.
- It needed **some way** to correlate Paystack webhooks to orders, so it added `payment_reference` directly.
- The new payments system introduced `Sale` as a generic payment object.

### 4.3 Does centralizing on `Sale` cause issues?

If done carefully, no – it’s an improvement:

- **Pros:**
  - Single place (`Sale`) for:
    - payment provider refs,
    - split config,
    - refund status,
    - association with ledger.
  - `Order` becomes purely a **business object** that:
    - optionally references `Sale`,
    - updates its status based on `Sale`/webhooks, but doesn’t need to know Paystack details.
- **Cons / work to do:**
  - Migration:
    - Add `sale` FK to `Order`.
    - Backfill it for existing orders using `payment_reference`.
  - Update **webhooks** to go via `payments.webhooks.paystack` and then update orders via Sale ID or metadata.

So you’re thinking about `Sale` correctly: it is higher‑level than orders and should eventually be the **one canonical payment object** across your system.

---

## 5. End‑to‑end testing strategy (menu → order → sale → split → withdraw)

You asked for a way to **test the entire flow**, with Paystack test APIs only. Here’s a concrete plan.

### 5.1 Local / CI setup

- Use **Paystack test keys**:
  - `PAYSTACK_SECRET_KEY=sk_test_xxx`
  - Optionally configure a public key for any client‑side pieces.
- Point the webhook URL in Paystack’s test dashboard to your dev/CI server (ngrok or similar), or:
  - In tests, **mock** Paystack HTTP calls + webhooks rather than calling real endpoints.

### 5.2 Suggested integration test cases

You can add a `tests/integration/test_payments_flows.py` with tests like:

1. **Happy path: order paid, split, driver withdraws realtime**
   - Arrange:
     - Create `Order` with:
       - orderer (customer profile),
       - branch,
       - driver.
   - Act:
     - Call the order accept API (`ResturantOrderView.accept_order`) to:
       - confirm order,
       - initialize Paystack transaction.
     - Simulate Paystack `charge.success`:
       - Either by:
         - calling `payments.webhooks.paystack.handle_paystack_webhook` directly with a fake payload that has the correct `paystack_reference`, or
         - hitting `payments.views.paystack_webhook_view` with a signed payload.
     - Call a “service complete” endpoint (order delivered) and trigger:
       - `payments.services.sale_service.complete_service`.
     - For the driver:
       - Use `driver_api.views.DriverWithdrawListCreateView.post` to request a withdrawal (with idempotency key).
       - Let Celery task `driver_api.tasks.process_withdrawal` run (in tests, you can call the task function directly).
       - Monkeypatch `PaystackClient.initiate_transfer` to simulate success and set a transfer ref.
     - Simulate Paystack transfer webhook:
       - Call `payments.webhooks.paystack.handle_paystack_webhook` with `transfer.success` event, referencing the transfer.
   - Assert:
     - `Sale` is `completed`.
     - Ledger entries exist for driver/business/referral splits.
     - `Withdrawal` is `complete`.
     - `DriverWithdrawalRequest` is `PAID`.
     - Balances/metrics look as expected.

2. **Refund flow: sale refunded after completion**
   - Similar as above, but:
     - Call `payments.views.refund_sale_view`.
     - Simulate `refund` behaviour (mock Paystack refund).
     - Assert:
       - `Sale.status == "refunded"`.
       - Appropriate ledger reversals happened.

3. **Idempotency behaviour end‑to‑end**
   - For both:
     - `initialize_sale_view`.
     - `request_withdrawal_view`.
   - In each case:
     - Send two identical requests with same `Idempotency-Key`.
     - Assert:
       - first returns `201`, second `200` with same body,
       - only one DB object is created.

All Paystack calls in these tests should:

- Either use real test keys but be localized (slower, but real), or
- Use `monkeypatch` to replace `PaystackClient` methods with fakes that return realistic payloads.

---

## 6. Simulating attacks and breaches – incident response sketch

Here’s a **practical incident response outline** tailored to your architecture.

### 6.1 Threat scenarios to test

1. **Replay / duplicate payment requests**
   - Attacker or buggy client retries `initialize_sale` or `withdrawal` many times.
   - Expected resilience:
     - Idempotency keys prevent duplicate sales/withdrawals.
     - Webhook dedup prevents multiple processing of the same Paystack event.

2. **Tampering with ledger or withdrawal rows**
   - Bad actor with DB access changes amounts, statuses, or recipients.
   - Expected detection:
     - `LedgerEntry.row_hash` no longer matches → hash verification fails.
     - `run_reconciliation` shows mismatches in amount/status/recipient, flagged as `high`/`critical`.

3. **Webhook forgery**
   - Attacker sends fake `charge.success` / `transfer.success` requests.
   - Expected resilience:
     - HMAC signature check fails → 400 and `invalid_signature` metrics increase.
     - No `Sale`/`Withdrawal` state changes.

4. **Partial failures in payout**
   - Network issues or Paystack downtime cause `execute_realtime` or `bulk_transfer` to fail or time out.
   - Expected behaviour:
     - Retries happen within the unified bridge.
     - After N retries, withdrawal is marked failed and flagged for manual review.
     - Reconciliation catches mismatches between Paystack and local state.

### 6.2 Incident response steps

When something looks wrong (alarms, customer report, or reconciliation mismatch):

1. **Freeze further risk**:
   - Temporarily:
     - disable new withdrawals for the affected user(s) or role,
     - optionally pause new payouts globally if the issue looks systemic.

2. **Gather evidence**:
   - Query:
     - `PaystackWebhookLog` for affected references.
     - `LedgerEntry` rows for affected users (verify hashes).
     - `Withdrawal` statuses and `ReconciliationLog` entries for recent days.

3. **Classify the issue**:
   - Single user vs many users?
   - Only one role (drivers vs businesses) or across roles?
   - Only one provider account (you currently have one)?

4. **Corrective actions**:
   - If extra payouts happened:
     - log them clearly,
     - consider reversing via future payouts or off‑line reconciliation.
   - If payouts were missed:
     - trigger manual payouts via Paystack dashboard or a one‑off batch.

5. **Hardening**:
   - Add:
     - more specific reconciliation checks,
     - alerts directly from:
       - `payments.webhook.error_total`,
       - `payments.payout.failed_total`,
       - high‑severity mismatches in `ReconciliationLog`.
   - Tighten DB permissions so only the app can write ledger/withdrawal rows.

You can dry‑run many of these steps in a staging environment by **simulating** Paystack responses and DB tampering while using the test keys.

---

## 7. Migration plan: align `menu` order payments with `Sale`/escrow

Goal: make `Order` rely on the **unified `payments.Sale` + escrow** design, and route all Paystack events through `payments.webhooks.paystack` instead of `menu.payment_views.paystack_webhook`.

### 7.1 Phase 0 – housekeeping

1. **Add a deprecation note** around:
   - `menu.payment_views.paystack_webhook` (order‑local webhook).
   - Anywhere that directly uses `paystackapi` instead of `PaystackClient` (already fixed for `menu.payment_services`).
2. **Ensure tests are green** for:
   - `payments/tests`,
   - `driver_api/tests`.

### 7.2 Phase 1 – Link `Order` to `Sale`

1. **Add FK on `Order`** (plus migration):

```python
class Order(models.Model):
    ...
    sale = models.ForeignKey("payments.Sale", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
```

2. **When accepting an order** (`ResturantOrderView.accept_order`):
   - Instead of calling `initialize_paystack_transaction` directly and only setting `payment_reference`, do:
     - Call `payments.views.initialize_sale_view` or, preferably, `payments.services.sale_service.initialize_sale` **from inside a dedicated service** that:
       - uses the order’s:
         - customer (payer),
         - branch/business owner,
         - driver (if assigned),
         - total amount.
     - Create a `Sale` with:
       - `payer` = customer’s `User`,
       - `business_owner` = restaurant admin `User`,
       - `driver` = assigned driver `User` (if any),
       - `referral_user` = from referral system if applicable.
     - Set:
       - `order.sale = sale`,
       - `order.payment_reference = sale.paystack_reference` (for compatibility).

3. **Keep `menu.payment_services.initialize_paystack_transaction` as a thin wrapper**:
   - Or better, call `sale_service.initialize_sale` directly from the order flow.

### 7.3 Phase 2 – Route order payment status via `payments.webhooks.paystack`

1. **Stop using `menu.payment_views.paystack_webhook` as the primary driver**:
   - Keep it only as a compatibility layer temporarily.
2. **Extend `payments.webhooks.paystack.process_event` for `charge.success`**:
   - After updating `Sale.status="in_escrow"`, also:
     - Find related `Order` via:
       - `Sale.metadata["order_id"]`, or
       - `Order.objects.filter(sale=sale)` if you have an FK.
     - Update `Order` status:
       - `confirmed`/`payment_pending` → `preparing`.
     - Create `OrderEvent` and broadcast websockets (move logic from `menu.payment_views`).
3. **Mark `menu.payment_views.paystack_webhook` as deprecated** and:
   - In staging, ensure **only** `payments.webhooks.paystack` is called from Paystack.

### 7.4 Phase 3 – Split & ledger fully driven from `Sale`

1. Ensure that wherever a service is “completed”:
   - You call `payments.views.complete_service_view` or `sale_service.complete_service(sale_id)`.
   - This:
     - uses `sale.split_snapshot`,
     - credits all parties via ledger,
     - transitions `Sale.status` to `completed`.
2. Optionally:
   - Store a link from `LedgerEntry` back to `Order` (via metadata) for easier reporting, but keep the canonical accounting in `Sale`/`LedgerEntry`.

### 7.5 Phase 4 – Remove legacy bits

Once your tests and real traffic in production confirm things are stable:

1. **Delete or hard‑disable**:
   - `menu.payment_views.paystack_webhook`.
   - Any old `files/*` payment helpers still referenced in code or docs.
2. **Clean up compatibility wrappers**:
   - If `payments/services/sale_service.py` still re‑exports from `files.sale_service`, replace with the in‑app implementation (which you already have under `try/files/sale_service.py`).
3. **Update documentation**:
   - Make it clear that:
     - All entrypoints for payment logic are in the `payments` app.
     - `Order` is a consumer of `Sale`, not a direct peer of Paystack.

At the end of this migration, your picture becomes:

- `Order` creates / references a `Sale`.
- `Sale` and `LedgerEntry` are the only places that know about amounts, splits, or Paystack references.
- Drivers and businesses get withdrawals only via the unified `Withdrawal` → Paystack flow.
- All Paystack webhooks enter through `payments.webhooks.paystack` and fan out to `Sale`, `Withdrawal`, and then to `Order`/driver as needed.

