# Coupons Discount App

This app owns coupon definitions and coupon-wheel mechanics.

## What this app owns

- `Coupons`: coupon rules and applicability.
- `CouponWheel`: a pool of coupons that can be spun or awarded.

## Mental model

- Coupons are configurable discount rules.
- A coupon can target:
- delivery
- a single menu item
- a menu category
- buy-X-get-Y flows

## Relationships that matter

- `Coupons` can point to `menu.MenuCategory`.
- `Coupons` can point to `menu.MenuItem`.
- `Coupons` can belong to an `accounts.Business`.
- `menu.Order` stores the chosen coupon.

## Scope model

- `global`: platform-wide coupon
- `business`: coupon restricted to one business

## Remember this when coming back

- This app defines discount rules.
- It does not compute final order totals by itself; order/payment flows consume it.
- If a discount bug depends on what a coupon means, start here.
