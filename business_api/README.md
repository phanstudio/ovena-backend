# Business API App

This app is the authenticated business-owner control surface after onboarding.

## What this app owns

- Branch operating-hours endpoints.
- Business payout info read/update endpoints.
- Business wallet balance and withdrawal endpoints.
- Small admin update serializers and base admin view helpers.

## Mental model

- `accounts` creates the business and branches.
- `business_api` is where a business admin manages them later.

## Relationships that matter

- Uses `accounts.BusinessAdmin`, `Branch`, `BranchOperatingHours`, and `BusinessPayoutAccount`.
- Uses `payments` for wallet balance and withdrawals.
- Protected by `authflow.CustomBAdminAuth` and `IsBusinessAdmin`.

## What this app does not own

- It does not create the business itself.
- It does not own the menu tree.
- It does not own payment ledger internals.

## Remember this when coming back

- Think of this app as the business owner's dashboard/backend APIs.
- If the action is "admin updates branch hours or requests payout", start here.
