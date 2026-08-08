"""
Changes to merge into payments/services/sale_service.py.

1. process_refund(): status guard now also accepts "paid". A sale captured
   by Paystack but not yet moved to "in_escrow" still has money sitting
   with us and nothing credited to anyone -- it needs to be refundable the
   same way "in_escrow" is. Nothing else about the function changes: the
   ledger-reversal branch still only fires for "completed", because that's
   the only status where credit_all_parties() has actually run.

2. process_refund(): now calls record_sales_penalty() when responsible_party
   is "business" or "driver". This was previously imported at the top of
   the file (`from accounts.services.penalties import record_system_penalty`)
   but never called -- dead import, now used via the fixed penalties.py.

3. New cancel_sale(): the entry point for order cancellations, as opposed
   to post-delivery disputes (which should keep calling process_refund
   directly with a deliberately chosen responsible_party).

   OPEN QUESTION -- sale.status == "pending" case:
   Nothing was ever captured by Paystack, so there's no refund transaction
   to issue. I close it out by setting sale.status = "refunded" with
   amount_refunded = 0, so cancelled-before-payment sales are still
   queryable next to real refunds instead of being left in "pending"
   forever. If you'd rather distinguish "never charged" from "charged then
   refunded" in reports, add a "cancelled" choice to Sale.STATUS_CHOICES
   and use that here instead -- small migration, your call, didn't want to
   change your schema without asking.
"""
import logging

from django.db import transaction
from django.utils import timezone

from payments.models import Sale
from payments.services.split_calculator import reverse_ledger_entries
from accounts.services.penalties import record_sales_penalty

logger = logging.getLogger(__name__)


@transaction.atomic
def process_refund(sale_id, reason, responsible_party: str = "business", responsible_party_reason: str = ""):
    """
    STEP 3 (if needed): Refund the user.
    Reverses ledger entries (based on responsible party fault), calls Paystack refund API,
    awards compensation points to the customer, and penalizes the responsible party.
    """
    from points.service import award_refund_compensation

    sale = Sale.objects.select_for_update().get(id=sale_id)

    if sale.status == "refunded":
        raise ValueError("Already refunded")
    # "paid" added: captured but not yet escrowed -- nothing's been credited
    # to anyone yet, so this is a plain Paystack reversal same as in_escrow.
    if sale.status not in ("paid", "in_escrow", "completed"):
        raise ValueError(f"Cannot refund sale with status: {sale.status}")

    if sale.status == "completed":
        reverse_ledger_entries(sale, reason, responsible_party=responsible_party)

    # Award compensation points to customer
    try:
        award_refund_compensation(
            user=sale.payer,
            sale=sale,
            idempotency_key=f"refund_comp:{sale.id}",
            points=sale.total_amount / 100,
        )
        sale.status = "refunded"
        sale.refunded_at = timezone.now()
        sale.refund_reason = reason
        sale.responsible_party = responsible_party
        sale.responsible_party_reason = responsible_party_reason
        sale.save()
    except Exception as e:
        # Log or handle points award failure gracefully without rolling back the financial refund
        logger.error(f"Failed to award refund compensation points for sale {sale.id}: {e}")

    # Penalize whoever's at fault. "platform" fault penalizes no one.
    if responsible_party in (Sale.RESPONSIBLE_BUSINESS, Sale.RESPONSIBLE_DRIVER):
        try:
            record_sales_penalty(sale)
        except Exception as e:
            logger.error(f"Failed to record penalty for sale {sale.id}: {e}")

    return {
        "success": True,
        "amount_refunded": sale.total_amount / 100,
        "responsible_party": responsible_party,
    }


@transaction.atomic
def cancel_sale(sale_id, reason, responsible_party: str = "platform", responsible_party_reason: str = ""):
    """
    Entry point for order cancellations. Post-delivery disputes should keep
    calling process_refund directly, not this.

    - status == "refunded": idempotent no-op (replay-safe).
    - status == "pending": nothing was ever captured -- close it out with
      amount_refunded = 0, no Paystack call. See module docstring re:
      whether you want a distinct "cancelled" status instead.
    - status in ("paid", "in_escrow"): money captured, nothing credited yet
      -> delegate to process_refund for the real reversal.
    - status == "completed": refused. Money has already been split out to
      the business/driver -- this is a dispute, not a cancellation. Call
      process_refund directly with a deliberately chosen responsible_party.
    """
    sale = Sale.objects.select_for_update().select_related("order").get(id=sale_id)

    if sale.status == "refunded":
        return {"success": True, "already_cancelled": True}

    if sale.status == "pending":
        sale.status = "refunded"
        sale.refunded_at = timezone.now()
        sale.refund_reason = reason
        sale.responsible_party = responsible_party
        sale.responsible_party_reason = responsible_party_reason
        sale.save()

        if responsible_party in (Sale.RESPONSIBLE_BUSINESS, Sale.RESPONSIBLE_DRIVER):
            try:
                record_sales_penalty(sale, sale.order)
            except Exception as e:
                logger.error(f"Failed to record penalty for sale {sale.id}: {e}")

        return {"success": True, "amount_refunded": 0, "responsible_party": responsible_party}

    if sale.status in ("paid", "in_escrow"):
        return process_refund(
            sale_id,
            reason,
            responsible_party=responsible_party,
            responsible_party_reason=responsible_party_reason,
        )

    raise ValueError(
        f"Cannot cancel sale with status: {sale.status}. "
        f"Completed sales need a dispute review -- call process_refund directly."
    )
