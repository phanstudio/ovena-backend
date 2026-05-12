# Ovena Backend Design Document

Updated: 2026-05-09
Audience: engineers maintaining or extending the backend

## 1. Overview

Ovena Backend is a modular Django monolith for a delivery marketplace with four primary actor groups:

- Customers
- Drivers
- Business operators
- Internal administrators

The backend is designed around a few strong domain seams:

- `accounts` for identity and business structure
- `menu` for catalog and order execution
- `payments` for money movement and ledger integrity
- `business_api` and `driver_api` for role-specific operational surfaces
- `support_center`, `notifications`, `referrals`, and `coupons_discount` for secondary product capabilities

The system is not a microservice architecture. It is one deployable application with app-level separation, shared models, and service modules used as domain boundaries where possible.

## 2. Design Goals

## 2.1 Product goals

- Support end-to-end food ordering and delivery operations.
- Handle different actor journeys without duplicating the whole backend per role.
- Provide real-time order state visibility to customers, branches, and drivers.
- Support payouts and money tracking with better-than-ad-hoc accounting primitives.
- Allow onboarding and KYC-like data capture for businesses and drivers.

## 2.2 Engineering goals

- Keep product domains separated enough to evolve independently inside one codebase.
- Centralize money movement in one app rather than scattering it through order logic.
- Preserve auditability through event, ledger, webhook-log, and reconciliation records.
- Support asynchronous workflows through Celery instead of forcing everything into request time.
- Use WebSockets only where state fan-out materially improves the user experience.

## 3. Non-Goals

- This codebase is not a general-purpose marketplace platform.
- It is not currently designed as independently deployable services.
- It is not event-sourced end-to-end, even though some domains keep event-like records.
- It does not yet enforce one universally consistent permission model from framework defaults alone.

## 4. Architectural Style

The project is best described as a domain-partitioned Django monolith.

Reasons this fits:

- One database is shared across all apps.
- Cross-app foreign keys are used directly.
- HTTP, WebSocket, and Celery entrypoints all live in the same project.
- Shared deployment and configuration are centralized in `core`.

This style is a good fit for the current product stage because it keeps delivery speed high while still allowing the team to separate responsibilities by app and service module.

## 5. Major Components

## 5.1 `accounts`

Purpose:

- Identity
- role resolution
- business and branch structure
- onboarding state
- driver verification artifacts

Why it exists:

- Nearly every other app needs to know who the actor is and what organization they belong to.

Key design choice:

- The project uses a custom `User` model plus role/profile models, rather than packing everything into `User`.

## 5.2 `menu`

Purpose:

- Catalog structure
- menu availability
- order state
- order events
- chat
- realtime order coordination

Why it exists:

- Ordering is the product core and needs its own set of transactional models.

Key design choice:

- `BaseItem` is the canonical product unit, while `MenuItem` is the presentation/sales unit.
- Branch-specific availability is modeled separately as `BaseItemAvailability`.

## 5.3 `payments`

Purpose:

- Payment initialization
- payout orchestration
- ledger and reconciliation
- idempotency
- webhook durability

Why it exists:

- Money movement requires stricter semantics than general CRUD.

Key design choices:

- Payment idempotency is a first-class model.
- Sales, withdrawals, ledger rows, and webhook logs are tracked explicitly.
- Other domains call into `payments` rather than owning their own payout logic.

## 5.4 `business_api`

Purpose:

- Post-onboarding business admin control surface

Why it exists:

- Onboarding and daily business operations are different workflows.

Key design choice:

- Business operational APIs are separated from the raw domain models in `accounts`.

## 5.5 `driver_api`

Purpose:

- Driver operational, earnings, and withdrawal surfaces

Why it exists:

- Driver flows have distinct permissions, data needs, and payout behavior.

Key design choice:

- Driver financial state is represented both in driver-local models and bridged into the shared payments system.

## 5.6 `support_center` and `notifications`

Purpose:

- Cross-cutting operational communications

Why they exist:

- Support and notifications need to be accessible from driver, business, and admin surfaces without duplicating API logic.

Key design choice:

- APIs are mounted into actor-specific namespaces instead of exposing one flat support/notification API.

## 6. Data Design

## 6.1 Identity model

The identity model is layered:

- `User` is the authenticated principal.
- `ProfileBase` provides a normalized profile anchor.
- specialized profiles represent actor-specific state.

This design supports:

- one authentication backbone
- multiple actor types
- referrals and actor resolution across domains

Tradeoff:

- More joins and more care required when resolving "who is the current actor?"

## 6.2 Business structure

The business structure is:

- `Business`
- `Branch`
- `BranchOperatingHours`
- `BusinessAdmin`
- `PrimaryAgent`
- linked staff relationships

This is a reasonable design for a multi-branch operator model because it separates ownership from branch-level operations.

Tradeoff:

- Naming drift between business/restaurant terminology increases cognitive load.

## 6.3 Catalog model

The catalog model distinguishes:

- reusable business-owned product definitions
- menu presentation
- variant/addon pricing
- branch-specific operational overrides

This is a strong choice because it prevents branch availability concerns from distorting the core product model.

Tradeoff:

- Query complexity grows because order pricing depends on menu data plus availability overrides.

## 6.4 Order model

`Order` owns lifecycle status, payment references, totals, timestamps, and participant relationships.

Supporting models:

- `OrderItem`
- `OrderEvent`
- `ChatMessage`

This gives the system:

- transactional order detail
- lightweight audit trail
- a place to fan out realtime messages

Tradeoff:

- The order domain is tightly coupled to payments and dispatch state, so changes here ripple easily.

## 6.5 Payments model

The payments model separates:

- commercial sale
- ledger explanation
- payout movement
- idempotency control
- webhook intake
- reconciliation evidence

This is one of the better-structured parts of the codebase because it recognizes that "payment succeeded" is not enough; the system also needs internal bookkeeping and replay safety.

Tradeoff:

- Direct cross-app references mean payment boundaries are logical, not hard technical boundaries.

## 7. Request, Realtime, and Background Design

## 7.1 HTTP request design

The request layer is organized by actor-facing namespaces:

- `/api/accounts/`
- `/api/business/`
- `/api/driver/`
- `/api/admin/`
- `/api/menu/`
- `/api/coupons/`
- `/api/referrals/`
- root-mounted payment routes

This keeps clients simple because each app can target its own role namespace.

Tradeoff:

- Some shared concerns, especially wallet flows, appear in more than one namespace.

## 7.2 WebSocket design

WebSockets are limited to the order/dispatch problem:

- per-order state room
- per-order chat room
- branch dashboard room
- driver order feed
- driver location channel

This is a good boundary. It avoids turning WebSockets into a second API for everything.

Tradeoff:

- Auth is custom middleware driven and deserves ongoing hardening.

## 7.3 Background work

Celery is used for:

- async order/payment operations
- payout execution
- verification and delayed workflows
- reconciliation and support tasks where needed

This is the right choice for workflows that involve external providers and time-based state changes.

Tradeoff:

- Background correctness depends on idempotency and state checks being consistently enforced.

## 8. Security and Integrity Considerations

## 8.1 Strengths

- JWT-based auth is standardized at the framework level.
- Password hashing configuration is modern.
- Payment idempotency exists as a dedicated mechanism.
- Private/public storage separation exists.
- Webhook logging and reconciliation are explicitly modeled.

## 8.2 Risks

- DRF default permission classes are not globally restrictive.
- A lot of security posture depends on every view correctly setting permission/auth classes.
- Custom auth decorators and custom auth classes increase flexibility, but also widen the audit surface.
- WebSocket auth is custom and should be treated as a critical security boundary.

## 9. Operational Design

The system expects external infrastructure for:

- Redis
- PostGIS database
- S3-compatible media storage
- Paystack
- SMS and email providers

Observability exists in pieces:

- optional Prometheus
- payment reconciliation artifacts
- some metrics helpers

Gaps:

- the repo notes and code comments still point to needing stronger error handling and monitoring, especially in order flow and payouts.

## 10. Design Tradeoffs

## 10.1 What the current design does well

- Fast product iteration inside one codebase
- clear enough domain separation for a growing team
- money logic treated as a special domain
- actor-specific API surfaces
- realtime limited to genuinely realtime features

## 10.2 What the current design makes harder

- enforcing uniform auth/permission patterns
- keeping documentation synchronized with route growth
- reasoning about cross-app model coupling
- maintaining naming consistency
- deciding which code-present modules are truly product features versus experiments or future work

## 11. Recommended Evolution Path

## 11.1 Near-term

1. Audit every mutating endpoint for explicit permission classes.
2. Decide the fate of `ratings` and `verification`.
3. Normalize naming around `business` versus `restaurant`.
4. Add automated route-map checks.
5. Strengthen operational logging around orders, payouts, and provider failures.

## 11.2 Mid-term

1. Reduce support-domain fragmentation between `driver_api` and `support_center`.
2. Extract clearer service-layer interfaces between `menu`, `payments`, and `driver_api`.
3. Define a single canonical payout workflow for driver, business, and referral payouts.
4. Expand observability around websocket sessions, task retries, and webhook replay events.

## 11.3 Long-term

1. Consider whether money movement should remain in the monolith or be isolated behind a stronger internal boundary.
2. Consider read-model or analytics-specific layers if dashboard/reporting complexity keeps increasing.
3. Consider generated docs for routes and schemas to reduce manual drift.

## 12. Recommended Reading Order for New Contributors

1. `core/settings.py`
2. `api/urls.py`
3. `accounts/README.md`
4. `menu/README.md`
5. `payments/README.md`
6. `driver_api/README.md`
7. `business_api/README.md`
8. `ARCHITECTURE_BLUEPRINT.md`

## 13. Summary

Ovena Backend is a reasonably well-partitioned Django monolith whose strongest design ideas are:

- role-aware identity modeling
- explicit order lifecycle modeling
- centralized payment and ledger logic
- targeted realtime coordination

Its main architectural challenges are not lack of structure, but consistency:

- consistent permissions
- consistent naming
- consistent documentation
- consistent boundaries between related operational domains

That makes the next phase of work less about inventing a new architecture and more about tightening the one that already exists.
