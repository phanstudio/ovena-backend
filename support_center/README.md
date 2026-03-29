# Support Center App

This app is the driver-support API layer.

## What this app owns

- FAQ list endpoints.
- Support ticket list/detail/message endpoints for drivers.
- Serializers and small support query helpers.

## Important architectural note

- The support models are currently defined in `driver_api.models`, not in this app.
- This app is a clean API surface over those models.

## Mental model

- `driver_api` owns the data.
- `support_center` owns the driver-facing support endpoints.

## Relationships that matter

- Support content and tickets are scoped to `accounts.DriverProfile`.
- FAQ categories/items, tickets, and ticket messages are stored in driver-api models.

## Remember this when coming back

- If you are changing support storage, check `driver_api`.
- If you are changing support endpoint behavior, check this app.
