# Authflow App

This app owns authentication, token shaping, profile-aware access control, and OTP utilities.

## What this app owns

- JWT authentication classes for different actor contexts.
- Permission classes such as `IsCustomer`, `IsDriver`, `IsBusinessAdmin`.
- Scope-based permissions for sub-user/device tokens.
- OTP request/verification helpers.
- Token creation helpers and delivery passphrase helpers.
- OpenAPI auth schema registration.
- Private storage helper used by business docs.

## Mental model

- Authentication here is not just "is the token valid?"
- It also answers "which profile is active on this request?"
- Permissions rely on the active profile in the token/header.

## Relationships that matter

- `accounts` provides the user and profile models.
- All business, driver, customer, and staff views rely on authflow classes.
- `menu` order delivery verification uses passphrase hashing here.

## Important concepts

- `active_profile` is central to role resolution.
- There are specialized auth classes for admin, driver, customer, and primary-agent style flows.
- Scope permissions are for constrained tokens such as linked devices or staff access.

## Remember this when coming back

- If a request is unexpectedly forbidden, check authflow first.
- If a view needs to know "which kind of actor is calling?", the answer is here.
- This app owns auth rules, not account data.
