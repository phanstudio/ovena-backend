# Support Center App

- we need an assigning service to either alert the support people or something?



Centralized support ticket and FAQ system for Drivers, Business Admins, and Customers. Designed for modularity, scalability, and real-time operations.

## Features

* **Multi-role Support Tickets**: Separate workflows for Drivers, Business Admins, and Customers.
* **Ticket Messages**: Support for threaded conversations per ticket.
* **FAQs**: Centralized, active-only FAQ listing.
* **Priorities & Statuses**: Tickets can be open, in-progress, resolved, or closed; priority levels: low, medium, high.
* **Pagination**: Supports limit-offset pagination for tickets and messages.
* **DRF ViewSets**: Reusable base classes for drivers and business admins.
* **Extensible Serializers**: Centralized serializer pattern for list, detail, create, and messages.
* **OpenAPI Documentation**: Fully documented via `drf-spectacular`, including messages endpoints.
* **Custom Auth & Permissions**: Supports `CustomDriverAuth` and `CustomBAdminAuth`, with role-based permissions.

---

## Models

### `SupportTicket`

| Field         | Type             | Notes                                            |
| ------------- | ---------------- | ------------------------------------------------ |
| `owner`       | ForeignKey(User) | Ticket creator                                   |
| `owner_role`  | CharField        | Choices: driver, business_admin, customer, staff |
| `category`    | CharField        | Default: "general"                               |
| `subject`     | CharField        | Ticket subject                                   |
| `description` | TextField        | Ticket content                                   |
| `status`      | CharField        | Choices: open, in_progress, resolved, closed     |
| `priority`    | CharField        | Choices: low, medium, high                       |
| `assigned_to` | ForeignKey(User) | Optional assignment                              |
| `created_at`  | DateTimeField    | Auto-added                                       |
| `updated_at`  | DateTimeField    | Auto-updated                                     |
| `closed_at`   | DateTimeField    | Optional                                         |

### `SupportTicketMessage`

| Field              | Type                      | Notes                                                      |
| ------------------ | ------------------------- | ---------------------------------------------------------- |
| `ticket`           | ForeignKey(SupportTicket) | Parent ticket                                              |
| `sender_type`      | CharField                 | Choices: driver, business_admin, customer, support, system |
| `sender`           | ForeignKey(User)          | Optional                                                   |
| `message`          | TextField                 | Message content                                            |
| `attachments_json` | JSONField                 | Optional attachments                                       |
| `created_at`       | DateTimeField             | Auto-added                                                 |

---

## Views / API

### Base Classes

* `BaseSupportTicketViewSet` – Generic ViewSet supporting list, retrieve, create, and messages.
* `BaseDriverSupportAPIView` – Handles driver-specific authentication and profile retrieval.
* `BaseBusinessSupportAPIView` – Handles business admin authentication and retrieval.

### Driver Endpoints

| URL                                       | Method    | Description                 |
| ----------------------------------------- | --------- | --------------------------- |
| `/api/driver/help/faqs/`                  | GET       | List active FAQs            |
| `/api/driver/help/tickets/`               | GET, POST | List/create tickets         |
| `/api/driver/help/tickets/{id}/`          | GET       | Ticket details              |
| `/api/driver/help/tickets/{id}/messages/` | GET, POST | List/create ticket messages |

### Business Endpoints

| URL                                   | Method    | Description                 |
| ------------------------------------- | --------- | --------------------------- |
| `/api/support/tickets/`               | GET, POST | List/create tickets         |
| `/api/support/tickets/{id}/`          | GET       | Ticket details              |
| `/api/support/tickets/{id}/messages/` | GET, POST | List/create ticket messages |

---

## Serializers

Centralized serializer pattern:

* `TicketListSerializer` / `BusinessTicketListSerializer`
* `TicketDetailSerializer` / `BusinessTicketDetailSerializer`
* `TicketCreateSerializer` / `BusinessTicketCreateSerializer`
* `TicketMessageSerializer` / `BusinessTicketMessageSerializer`
* `TicketMessageCreateSerializer` / `BusinessTicketMessageCreateSerializer`
* `FAQItemSerializer`

> Each role-specific ViewSet overrides these serializer attributes, allowing **single base class logic**.

---

## Pagination

* Implemented via `SupportPagination` using DRF `LimitOffsetPagination`.
* Default limit: 20, max: 100.

---

## OpenAPI / Docs

* Uses `drf-spectacular` `@extend_schema` for:

  * Ticket creation
  * Ticket detail retrieval
  * Messages GET/POST endpoints
* Works with dynamic serializers per subclass via **class-level serializer attributes**.

---

## Permissions & Authentication

* Driver endpoints: `CustomDriverAuth`, `IsDriver`
* Business endpoints: `CustomBAdminAuth`, `IsBusinessAdmin`
* Tickets are filtered by **owner and role** automatically in base queryset.

---

## Services

Utility functions centralizing logic:

* `create_support_ticket(user, role, subject, message, category, priority)` – Creates a ticket and first message.
* `create_support_ticket_message(role, ticket, user, message, attachments_json)` – Adds message to a ticket.
* `get_active_faq_queryset()` – Returns only active FAQs.
* `Role` enum – Standardizes owner/sender roles across drivers and business admins.

---

## How to Add a New Role / System

1. Create new role in `Role` enum.
2. Create serializers for list, detail, create, and message.
3. Create a ViewSet inheriting `BaseSupportTicketViewSet` + role-specific base auth view.
4. Override serializer attributes and roles.
5. Plug the URL pattern in your route files.

> This pattern **avoids duplication** and centralizes all ticket/message logic for any new system.

---

## Example

```python
# urls.py
from django.urls import path, include
from support_center import views

driver_urlpatterns = [
    path("help/faqs/", views.DriverFAQListView.as_view(), name="driver-help-faqs"),
    path("help/tickets/", views.DriverSupportTicketViewSet.as_view({"get": "list", "post": "create"})),
    path("help/tickets/<int:pk>/messages/", views.DriverSupportTicketViewSet.as_view({"get": "messages", "post": "messages"})),
]
```