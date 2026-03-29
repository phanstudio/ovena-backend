# Payments App

This app owns money movement, sales, ledger integrity, idempotency, withdrawals, and payment-webhook recording.

## What this app owns

- `UserAccount`: payment-specific payout metadata for a user.
- `PlatformConfig`: mutable platform settings.
- `PaymentIdempotencyKey`: request replay protection.
- `Sale`: the commercial payment record.
- `LedgerEntry`: immutable accounting rows.
- `Withdrawal`: payout requests.
- `PaystackWebhookLog`: durable webhook intake record.
- `ReconciliationLog`: audit/reconciliation summaries.

## Mental model

- `Sale` represents money collected for a transaction.
- `LedgerEntry` explains where that money went.
- `Withdrawal` moves funds out to a user.
- `PaymentIdempotencyKey` prevents duplicate effects from retrying requests.

## Relationships that matter

- `Sale` links payer, business owner, optional driver, and optional referral user.
- `menu.Order` can point to a `Sale`.
- `driver_api.DriverWithdrawalRequest` can point to a `Withdrawal`.
- `business_api` uses the wallet/withdrawal services built here.

## Integrity model

- Ledger rows are intentionally immutable.
- Webhook logs are intended to be append-only/immutable after insert.
- Idempotency is first-class and used across payout flows.

## Remember this when coming back

- If the question is "what money moved and why?", start here.
- If the question is "can this request be safely retried?", start here.
- This app is the accounting/payment truth, not the business onboarding layer.
