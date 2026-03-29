# Ratings App

This app owns post-order ratings for drivers and branches.

## What this app owns

- `DriverRating`
- `BranchRating`
- shared abstract base `RatingBase`

## Mental model

- Ratings are tied to a specific order.
- A customer rates the delivery experience and/or branch experience after that order.
- Driver and branch ratings are separate records with separate complaint types.

## Relationships that matter

- `rater` is `accounts.CustomerProfile`.
- `order` is `menu.Order`.
- `driver` is `accounts.DriverProfile`.
- `branch` is `accounts.Branch`.

## Constraints to remember

- One customer cannot create duplicate driver ratings for the same order/driver pair.
- One customer cannot create duplicate branch ratings for the same order/branch pair.
- Driver/order or branch/order identity is not meant to mutate after creation.

## Remember this when coming back

- This app is about reputation history tied to fulfilled orders.
- If you need aggregate averages or counts, this app already has queryset helpers and index strategy for that.
