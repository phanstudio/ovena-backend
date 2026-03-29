# Verification App

This app is the integration layer for external identity and business verification checks.

## What this app owns

- Request serializers for verification inputs.
- Service wrappers for external verification provider calls.
- API views for driver and business verification endpoints.

## What it verifies

- Driver NIN
- Driver BVN
- Driver BVN validation
- Bank account number lookup
- Face match
- Plate number
- Business TIN
- Business RC number
- Business BVN

## Mental model

- This app does not own long-term driver/business profile state.
- It performs or proxies verification checks and returns results.
- Persistent onboarding state lives in `accounts`.

## Relationships that matter

- `accounts` consumes the results during onboarding and admin review flows.
- Driver verification records as durable business state live in `accounts.models.driver`.

## Remember this when coming back

- If the problem is "how do we talk to the verification provider?", start here.
- If the problem is "where do we store the approved/rejected outcome on our side?", also check `accounts`.
