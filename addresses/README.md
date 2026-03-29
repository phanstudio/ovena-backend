# Addresses App

This app owns geospatial location data.

## What this app owns

- `Address`: saved customer or reusable location record.
- `DriverLocation`: latest known GPS location for a driver.

## Mental model

- `Address` is a reusable place object.
- `DriverLocation` is operational live-state, not a historical log.

## Relationships that matter

- `CustomerProfile` in `accounts` links to `Address`.
- `DriverLocation` points to `accounts.DriverProfile`.
- Distance and nearest-driver logic rely on GIS fields here.

## Why this app exists

- Keeps GIS logic out of `accounts` and `menu`.
- Centralizes `PointField`, nearest-neighbor lookups, and radius filters.

## What other apps depend on this

- `accounts` uses `Address` for customer addresses.
- `menu` uses branch/customer coordinates for delivery distance.
- Driver dispatch or tracking features will rely on `DriverLocation`.

## Remember this when coming back

- If the problem is "where is this thing?" or "what is closest?", start here.
- This app is about coordinates and lookup, not business rules.
