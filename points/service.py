from __future__ import annotations

"""
payments/points/service.py

Public API:
  - get_points_balance(user)
  - award_referral_success(referrer, referred_user, idempotency_key)
  - award_referred_first_order(referrer, sale, idempotency_key)
  - award_order_streak(user, sale, streak_count, idempotency_key)
  - award_order_milestone_scratch_card(user, sale, order_number, scratched_points, idempotency_key)
  - award_order_rated(user, rating, idempotency_key)
  - reverse_points_award(entry, reason)
  - create_points_withdrawal_request(user, points_requested, idempotency_key)

Every write goes through _award_points(). Nothing else in the codebase
should create a PointsLedgerEntry directly -- that's the whole point of
having this file.
"""

import logging

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Sum

from points.models import PointsEventRule, PointsLedgerEntry, PointsWithdrawalRequest

logger = logging.getLogger(__name__)

MINIMUM_WITHDRAWAL_POINTS = 1000

# Fallback values used only if PointsEventRule hasn't been seeded yet for a
# given event type. Seed PointsEventRule in a migration/fixture for real
# deployments -- these constants exist so the service still works out of the
# box and so the launch values from the spec are recorded somewhere in code.
_DEFAULT_FLAT_POINTS = {
    PointsLedgerEntry.EVENT_REFERRAL_SUCCESS: 200,
    PointsLedgerEntry.EVENT_REFERRED_FIRST_ORDER: 1000,
    PointsLedgerEntry.EVENT_ORDER_STREAK_5: 250,
    PointsLedgerEntry.EVENT_ORDER_RATED: 20,
}
_DEFAULT_RANGE_POINTS = {
    PointsLedgerEntry.EVENT_ORDER_MILESTONE_5: (50, 500),
}


def get_points_balance(user) -> int:
    result = PointsLedgerEntry.objects.filter(user=user).aggregate(total=Sum("points"))
    return result["total"] or 0


def _flat_points_for(event_type: str) -> int:
    """Look up a flat point value: DB rule first, hardcoded default as fallback."""
    rule = PointsEventRule.objects.filter(event_type=event_type, is_active=True).first()
    if rule and rule.points_value is not None:
        return rule.points_value
    if event_type in _DEFAULT_FLAT_POINTS:
        return _DEFAULT_FLAT_POINTS[event_type]
    raise ValueError(f"No active flat points rule configured for '{event_type}'")


def _range_for(event_type: str) -> tuple[int, int]:
    """Look up a (min, max) range: DB rule first, hardcoded default as fallback."""
    rule = PointsEventRule.objects.filter(event_type=event_type, is_active=True).first()
    if rule and rule.min_points is not None and rule.max_points is not None:
        return rule.min_points, rule.max_points
    if event_type in _DEFAULT_RANGE_POINTS:
        return _DEFAULT_RANGE_POINTS[event_type]
    raise ValueError(f"No active ranged points rule configured for '{event_type}'")


@transaction.atomic
def _award_points(*, user, event_type: str, points: int, proof, idempotency_key: str, notes: str = ""):
    """
    Core primitive -- the only place that writes PointsLedgerEntry rows.

    - idempotency_key must be deterministic per event (e.g. built from the
      user id + the id of whatever triggered it) so retries/webhook replays
      never double-award.
    - proof is required conceptually: pass the Sale/Rating/User that caused
      this row. It's stored as a generic FK so it's queryable before any
      payout decision is made.
    """
    existing = PointsLedgerEntry.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        logger.info("points.ledger.replay", extra={"idempotency_key": idempotency_key})
        return existing

    entry = PointsLedgerEntry.objects.create(
        user=user,
        event_type=event_type,
        points=points,
        balance_after=get_points_balance(user) + points,
        proof_content_type=ContentType.objects.get_for_model(proof) if proof is not None else None,
        proof_object_id=str(proof.pk) if proof is not None else None,
        idempotency_key=idempotency_key,
        notes=notes,
    )
    logger.info(
        "points.ledger.created",
        extra={
            "user_id": str(user.id),
            "event_type": event_type,
            "points": points,
            "entry_id": str(entry.id),
        },
    )
    return entry


# ---------------------------------------------------------------------------
# Event API -- one function per earning rule. Adding a new rule = adding a
# new function here + a PointsEventRule row (via admin/API, no deploy needed
# for value changes to *existing* rules). Callers elsewhere in the codebase
# should never touch PointsLedgerEntry directly.
# ---------------------------------------------------------------------------

def award_referral_success(*, referrer, referred_user, idempotency_key: str):
    return _award_points(
        user=referrer,
        event_type=PointsLedgerEntry.EVENT_REFERRAL_SUCCESS,
        points=_flat_points_for(PointsLedgerEntry.EVENT_REFERRAL_SUCCESS),
        proof=referred_user,
        idempotency_key=idempotency_key,
    )


def award_referred_first_order(*, referrer, sale, idempotency_key: str):
    return _award_points(
        user=referrer,
        event_type=PointsLedgerEntry.EVENT_REFERRED_FIRST_ORDER,
        points=_flat_points_for(PointsLedgerEntry.EVENT_REFERRED_FIRST_ORDER),
        proof=sale,
        idempotency_key=idempotency_key,
    )


def award_order_streak(*, user, sale, streak_count: int, idempotency_key: str):
    """streak_count is the caller's running count; this only fires on multiples of 5."""
    if streak_count % 5 != 0:
        return None
    return _award_points(
        user=user,
        event_type=PointsLedgerEntry.EVENT_ORDER_STREAK_5,
        points=_flat_points_for(PointsLedgerEntry.EVENT_ORDER_STREAK_5),
        proof=sale,
        idempotency_key=idempotency_key,
        notes=f"Streak count {streak_count}",
    )


def award_order_milestone_scratch_card(
    *, user, sale, order_number: int, scratched_points: int, idempotency_key: str
):
    """
    scratched_points is whatever the scratch-card reveal produced. Validated
    against the configured range so a bug upstream can't award outside it.
    """
    if order_number % 5 != 0:
        raise ValueError("Scratch card milestone only fires on every 5th order")
    lo, hi = _range_for(PointsLedgerEntry.EVENT_ORDER_MILESTONE_5)
    if not (lo <= scratched_points <= hi):
        raise ValueError(f"Scratch card points must be between {lo} and {hi}")
    return _award_points(
        user=user,
        event_type=PointsLedgerEntry.EVENT_ORDER_MILESTONE_5,
        points=scratched_points,
        proof=sale,
        idempotency_key=idempotency_key,
        notes=f"Scratch card reveal on order #{order_number}",
    )


def award_order_rated(*, user, rating, idempotency_key: str):
    return _award_points(
        user=user,
        event_type=PointsLedgerEntry.EVENT_ORDER_RATED,
        points=_flat_points_for(PointsLedgerEntry.EVENT_ORDER_RATED),
        proof=rating,
        idempotency_key=idempotency_key,
    )


# ---------------------------------------------------------------------------
# Reversal -- never delete, insert a negative row that references the original
# ---------------------------------------------------------------------------

@transaction.atomic
def reverse_points_award(entry: PointsLedgerEntry, reason: str):
    if entry.points <= 0:
        raise ValueError("Only positive (credit) entries can be reversed")
    return _award_points(
        user=entry.user,
        event_type=PointsLedgerEntry.EVENT_ADJUSTMENT,
        points=-entry.points,
        proof=entry,
        idempotency_key=f"reversal:{entry.id}",
        notes=f"Reversal of {entry.id}: {reason}",
    )


# ---------------------------------------------------------------------------
# Redemption
# ---------------------------------------------------------------------------

@transaction.atomic
def create_points_withdrawal_request(*, user, points_requested: int, idempotency_key: str):
    if points_requested < MINIMUM_WITHDRAWAL_POINTS:
        raise ValueError(f"Minimum withdrawal is {MINIMUM_WITHDRAWAL_POINTS} points")

    existing = PointsWithdrawalRequest.objects.filter(
        user=user, ledger_entry__idempotency_key=idempotency_key
    ).first()
    if existing:
        return existing

    balance = get_points_balance(user)
    if points_requested > balance:
        raise ValueError("Insufficient points balance")

    hold_entry = _award_points(
        user=user,
        event_type=PointsLedgerEntry.EVENT_REDEMPTION,
        points=-points_requested,
        proof=None,
        idempotency_key=idempotency_key,
        notes="Hold for points withdrawal request",
    )
    return PointsWithdrawalRequest.objects.create(
        user=user,
        points_requested=points_requested,
        ledger_entry=hold_entry,
    )
