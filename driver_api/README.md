# Driver API App

This app is the driver-side operations domain.

## What this app owns

- `DriverWallet`: driver balance snapshot.
- `DriverLedgerEntry`: driver money movement log.
- `DriverWithdrawalRequest`: driver payout request lifecycle.
- Support domain models currently live here too:
- `SupportFAQCategory`
- `SupportFAQItem`
- `SupportTicket`
- `SupportTicketMessage`

## Mental model

- `accounts.DriverProfile` is the identity.
- `driver_api` is the operational state around work, money, notifications, and support.

## Relationships that matter

- Wallet and ledger are per driver.
- Withdrawal requests may link to `payments.Withdrawal`.
- Notifications belong to drivers.
- Support tickets and FAQ content are currently stored here, even though `support_center` exposes the APIs.

## API shape in this app

- Driver dashboard/profile/availability.
- Earnings summary and history.
- Withdrawal eligibility, create, list, and detail.
- Includes support-center and notifications driver URLs.

## Architectural note

- Support models are physically here, but `support_center` is the API layer around them.
- Notifications are stored in the `notifications` app; `driver_api` only triggers notifications via services.

## Remember this when coming back

- If the question is "what is the driver's current operational or money state?", start here.
- This app mixes wallet, support, and notifications data, so expect some cross-app surface with shared models.
