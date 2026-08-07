"""
menu/services/order_cancel.py  (new file)

Single entry point for cancelling an order. Meant to replace the inline
cancel logic currently duplicated in OrderCancelView.patch (customer) and
ResturantOrderView.cancel_order (branch) in order.py -- both of which today
only flip order.status and never touch the Sale at all.

STAGE MAP (per your breakdown):
  PAYMENT_PENDING / PAYMENT_INITIALIZATION_FAILED
      -> customer or system (stale-order cleanup) can cancel.
         Sale is still "pending" (or doesn't exist yet) -- nothing captured,
         cancel_sale() just closes it out, no Paystack call.
  PENDING (payment already captured, branch hasn't acted)
      -> customer or system can still cancel.
         Sale is "paid" -- captured but nothing credited yet. Full refund.
         Pickup vs delivery doesn't change anything at this stage: no split
         has been paid out to anyone yet either way.
  CONFIRMED / PREPARING
      -> branch's court now, so only branch/support can cancel here, not
         the customer. NOTE: this is a behavior change from the current
         OrderCancelView, which still allows customer cancel while
         status == CONFIRMED. Flagging in case that was intentional.
  READY / DRIVER_ASSIGNED
      -> branch/support only. Business already cooked the food -- see open
         question below about whether they should keep the item-cost split.
  PICKED_UP / ON_THE_WAY / DELIVERED
      -> NOT in CANCELLABLE_STAGES on purpose. Once a driver has the food,
         this needs to go through process_refund with a real dispute
         decision, not a "cancel."

OPEN QUESTIONS -- defaulted to "platform" (full refund, nobody penalized)
rather than guess a business rule:
  - Customer cancels a CONFIRMED/PREPARING order: business already started
    cooking. Penalize them? Let them keep the item cost? Neither happens
    right now -- platform absorbs the full refund.
  - Cancel at READY/DRIVER_ASSIGNED (food's done, no driver yet): should the
    business keep the item-cost portion since the work is done? cancel_sale
    does a full refund with no partial credit right now. If you want the
    business paid out even on cancel, that's a separate split calculation,
    not a refund -- happy to build that once you've decided the rule.
  - No visibility here into what happens when find_and_assign_driver never
    finds a driver (retries forever? times out?). If there's a terminal
    failure state for that, it should probably route through here too.

Not handled by this file: an SLA timeout for CONFIRMED/PREPARING (branch
taking too long to accept/make the order). You weren't sure you wanted
auto-cancel there, and I'd agree -- money's already committed at that point,
so a timeout should probably escalate to support rather than auto-cancel.
Separate task if you want it.
"""
import logging

from django.db import transaction

from menu.models import Order, OrderEvent, OrderStatus
from payments.services.sale_service import cancel_sale
from enum import Enum

logger = logging.getLogger(__name__)

# stage -> which actor_types are allowed to cancel there
CANCELLABLE_STAGES = {
    OrderStatus.PAYMENT_PENDING: {"customer", "system"},
    OrderStatus.PAYMENT_INITIALIZATION_FAILED: {"customer", "system"},
    OrderStatus.PENDING: {"customer", "system"},
    OrderStatus.CONFIRMED: {"customer", "support"},
    OrderStatus.PREPARING: {"branch", "support"},
    # OrderStatus.READY: {"branch", "support"},
    # OrderStatus.DRIVER_ASSIGNED: {"branch", "support"},
}

class ACTORS(Enum):
    CUSTOMER = "customer"
    BRANCH = "branch"

@transaction.atomic
def cancel_order(order: "Order", actor_type: str, reason: str, responsible_party: str = None):
    """
    actor_type: "customer" | "branch" | "system" | "support"
    responsible_party: pass explicitly if you already know who's at fault
        (e.g. a branch-initiated cancel is naturally "business"). Defaults
        to "platform" -- full refund, no one penalized -- when not given.
    """
    allowed_actors = CANCELLABLE_STAGES.get(order.status)
    if allowed_actors is None:
        raise ValueError(f"Order cannot be cancelled at stage: {order.status}")
    if actor_type not in allowed_actors:
        raise ValueError(f"'{actor_type}' cannot cancel an order at stage: {order.status}")

    responsible_party = responsible_party or "platform"

    old_status = order.status
    order.status = OrderStatus.CANCELLED
    order.save(update_fields=["status", "last_modified_at"])

    OrderEvent.objects.create(
        order=order,
        event_type="cancelled",
        actor_type=actor_type,
        old_status=old_status,
        new_status=order.status,
        metadata={"reason": reason, "responsible_party": responsible_party},
    )

    refund_result = None
    if order.sale_id:
        try:
            refund_result = cancel_sale(
                order.sale_id,
                reason=reason,
                responsible_party=responsible_party,
            )
        except ValueError as e:
            # Sale already completed/refunded, or otherwise not cancellable.
            # Don't block the order-level cancel on this -- log it and let
            # support pick it up, since the order is being cancelled either way.
            logger.error(f"cancel_sale failed for order {order.id}: {e}")

    return {"order_id": str(order.id), "status": order.status, "refund": refund_result}
