# Notifications App

This app owns the notifications domain (storage + API surface).

## What this app owns

- Driver notification list/read/unread endpoints.
- Notification serializers and small query/update services.

## Important architectural note

- Notifications are stored in `notifications.models.Notification` and scoped by `AUTH_USER_MODEL`.
- Driver-specific auth is exposed via `notifications.driver_urls` (used by `driver_api.urls`).

## Mental model

- Any app can create notifications by calling `notifications.services.create_notification(...)`.
- Clients read/list/mark-read notifications through `notifications` endpoints.

## Relationships that matter

- Everything is scoped to `request.user`.
- Role-specific endpoints differ only by auth/permissions (not by data model).

## Remember this when coming back

- If you are changing notification storage, check `notifications.models`.
- If you are changing notification endpoints or payload shape, check this app.
