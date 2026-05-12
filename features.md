# Ovena Backend Features

Updated: 2026-05-09
Scope: current codebase feature inventory

## 1. Platform capabilities

- Django 5.1 monolith with Django REST Framework APIs
- JWT-based authentication with refresh, rotation, and logout flows
- Role-specific auth patterns for customers, drivers, business admins, staff, and app admins
- WebSocket support for order events, branch dashboards, driver feeds, live location, and order chat
- Celery background task execution with Redis broker/result backend
- PostGIS-backed spatial data support
- Public and private object storage on S3-compatible infrastructure
- OpenAPI schema and Swagger docs via drf-spectacular
- Optional Prometheus metrics exposure

## 2. Customer-facing features

### Authentication and identity

- Phone OTP send and verify
- Email OTP send and verify
- Customer registration
- JWT login and token refresh lifecycle
- OAuth exchange flow
- Customer profile fetch
- Customer profile update
- Password reset support
- Account deletion endpoints

### Discovery and ordering

- Restaurant listing
- Homepage aggregation endpoint
- Menu listing by business
- Menu-item search
- Order creation
- Order detail retrieval
- Order cancellation
- Coupon application through the order domain

### Promotions and loyalty

- Referral code application
- Personal referral status view
- Personal referrals list
- Coupon wheel retrieval
- Coupon wheel spin

### Realtime experience

- Order status subscriptions over WebSocket
- Order chat between participants

## 3. Business-facing features

### Business onboarding

- Business admin registration
- Business admin re-registration
- Multi-phase business onboarding
- Business onboarding status tracking
- Batch image/upload URL generation for onboarding assets
- Menu registration as part of onboarding

### Business operations

- Business dashboard
- Store analysis endpoint
- Business profile/admin update flow
- Business image update flow
- Branch create/update
- Branch listing
- Branch delete
- Branch hours management
- Per-branch close/open controls
- Close-all-branches operation
- Staff list
- Staff revoke

### Menu management

- Business menu list
- Staff menu list
- Menu update endpoint
- Availability list by branch
- Availability bulk update
- Bulk menu delete
- Single delete for menu, category, item, and addon

### Business finance

- Business payout destination setup/update
- Payment receiver verification
- Transaction PIN management
- Wallet balance
- Wallet transaction history
- Withdrawal eligibility
- Wallet withdrawal request
- Wallet withdrawal history

### Business support and notifications

- Business support tickets
- Business staff support tickets
- Business notification feed

## 4. Driver-facing features

### Driver onboarding and identity

- Driver login
- Multi-phase driver onboarding
- Driver onboarding status endpoint
- Driver KYC/document/bank data capture

### Driver operations

- Driver dashboard
- Driver profile fetch/update
- Driver availability update
- Driver order interaction surface
- Driver performance analysis
- Live location WebSocket channel
- Driver assignment/order feed WebSocket channel

### Driver earnings and payouts

- Earnings summary
- Earnings history
- Withdrawal eligibility
- Withdrawal create/list
- Withdrawal detail
- Driver wallet and ledger domain models

### Driver support and notifications

- Driver FAQ list
- Driver support tickets
- Driver notifications

## 5. Admin/internal features

- App admin login
- App admin profile and profile update
- Admin dashboard statistics
- User list and detail
- Driver list
- Driver onboarding review
- Business list
- Business update
- Withdrawal list and detail
- Withdrawal retry
- Withdrawal mark-paid
- Withdrawal mark-failed
- Batch withdrawal execution
- Withdrawal reconciliation
- Notification list
- Targeted notification send
- Admin support tickets
- Referral payout admin operations
- Coupon creation and update
- Coupon wheel creation and update

## 6. Payments and accounting features

- Payment initialization for sales
- Sale completion endpoint
- Refund endpoint
- Paystack webhook intake
- Payment-specific wallet endpoints
- Immutable-style ledger model
- Idempotency-key persistence for replay protection
- Reconciliation log model and reconciliation service
- Driver-withdrawal bridge into the shared payments withdrawal engine

## 7. Supporting domain features

- Notification persistence with read/list semantics
- Support tickets with threaded messages
- Support ticket ownership for driver, business admin, business staff, and customer roles
- Branch geospatial storage
- Driver location storage
- Routing backend abstraction for ORS, Mapbox, and Google

## 8. Code-present but not live from the root API graph

- Ratings APIs exist in `ratings/urls.py` but are not mounted
- `verification` module exists in the repository but is not installed or routed

## 9. Incomplete or evolving areas visible in code/comments

- Permissions are not uniformly locked down by a global DRF default
- Business versus restaurant naming is still mixed
- Support ownership is split between `driver_api` and `support_center`
- Some README and planning notes indicate ongoing work around:
  - payout strategy
  - verification hardening
  - monitoring
  - fallback messaging
  - improved error handling in order and payment flows

## 10. Feature status summary

| Area | Status |
| --- | --- |
| Accounts/auth | Live |
| Business onboarding | Live |
| Business operations | Live |
| Customer ordering | Live |
| Driver operations | Live |
| Payments and withdrawals | Live |
| Notifications | Live |
| Support center | Live |
| Coupons and referrals | Live |
| Ratings | Code-present, not mounted |
| Verification app | Code-present, not active |
