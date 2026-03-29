# Notifications App

This app is the driver-notification API layer.

## What this app owns

- Driver notification list/read/unread endpoints.
- Notification serializers and small query/update services.

## Important architectural note

- The `DriverNotification` model is not defined here.
- The data model currently lives in `driver_api.models`.
- This app is a focused delivery layer around that model.

## Mental model

- `driver_api` owns notification data.
- `notifications` owns the read/list API surface.

## Relationships that matter

- Everything here is scoped to `accounts.DriverProfile`.
- Views use the driver auth context and then query `driver_api.DriverNotification`.

## Remember this when coming back

- If you are changing notification storage, check `driver_api`.
- If you are changing notification endpoints or payload shape, check this app.
