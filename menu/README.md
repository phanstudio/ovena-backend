# Menu App

This app owns the product catalog, menu structure, availability hooks, and order lifecycle.

## What this app owns

- Catalog/menu models:
- `BaseItem`
- `Menu`
- `MenuCategory`
- `MenuItem`
- `VariantGroup`
- `VariantOption`
- `MenuItemAddonGroup`
- `MenuItemAddon`
- `BaseItemAvailability`
- Order models:
- `Order`
- `OrderItem`
- `OrderEvent`
- `ChatMessage`

## Mental model

- `BaseItem` is the canonical business-owned product definition.
- `MenuItem` is how that product is presented and sold in a menu.
- `BaseItemAvailability` is the branch-specific operational override for that product.
- `Order` and `OrderItem` are the transactional side built on top of the menu tree.

## Relationships that matter

- `Business -> Menu -> MenuCategory -> MenuItem`
- `MenuItem -> BaseItem`
- `MenuItem -> VariantGroup -> VariantOption`
- `MenuItem -> MenuItemAddonGroup -> MenuItemAddon -> BaseItem`
- `Branch + BaseItem -> BaseItemAvailability`
- `Order -> Branch / Customer / Driver`
- `OrderItem -> MenuItem`

## Creation/update flow

- Menu registration and batch updates build the menu tree.
- Base items are reused by business and name.
- Base-item availability is bootstrapped for every branch when a base item first appears.
- Order pricing prefers branch `BaseItemAvailability.override_price`, then falls back to menu/base pricing.

## Important current behavior

- Branch availability is modeled at `BaseItemAvailability`, not directly on `MenuItem`.
- `Menu.is_active` controls whole-menu visibility.
- `MenuItem` currently does not have its own `is_active`.

## What other apps depend on this

- `coupons_discount` points to menu categories/items.
- `ratings` points to orders.
- `payments` links to order sales.
- `accounts` supplies business, branch, customer, and driver identities.

## Remember this when coming back

- If you are changing catalog structure, start with `BaseItem` and `MenuItem`.
- If you are changing branch stock/availability, think `BaseItemAvailability`.
- If you are changing customer ordering flow, start in `order.py` and the order serializers/views.
