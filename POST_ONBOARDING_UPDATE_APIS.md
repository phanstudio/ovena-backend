# Post-Onboarding Update APIs (Business Admin)

These endpoints let a business admin update onboarding-related data after onboarding is complete.

## Auth

- Requires a valid business-admin JWT (`Authorization: Bearer <access>`)
- Most endpoints use `CustomBAdminAuth` + `IsBusinessAdmin`

## Business profile (phase 1/2 fields)

- `GET /api/business/profile/` — fetch business + KYC snapshot
- `PUT /api/business/profile/` — update business fields and/or KYC fields (partial)
  - Supports multipart form-data for:
    - `business_image` (file)
    - `business_documents` (file)

## Branches (phase 2)

- `GET /api/business/branches/` — list branches
- `POST /api/business/branches/` — create a branch (optionally include `operating_hours`)
- `GET /api/business/branches/<branch_id>/` — branch details
- `PUT /api/business/branches/<branch_id>/` — update branch fields (partial)
- `GET /api/business/branches/<branch_id>/hours/` — list operating hours
- `PUT /api/business/branches/<branch_id>/hours/` — replace operating hours

## Payment (phase 2)

- `GET /api/business/payment/`
- `PUT /api/business/payment/`

## Menus (phase 3)

Two supported options:

- `PUT /api/business/menus/replace/` — deletes existing menus for the business and imports the new menu tree
- `PUT /api/accounts/onboard/phase3/` — same behavior (menu tree replace) using the onboarding phase-3 payload

