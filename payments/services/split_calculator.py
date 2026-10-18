"""
split_calculator.py - handles split logic, ledger credits, row hashing
"""
import logging
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


def _bps(pct: float | int) -> int:
    """Converts a percentage (e.g. 15.5 or 0.29) to integer basis points (1550, 29)."""
    return round(float(pct) * 100)


def load_split_config():
    from payments.models import PlatformConfig
    keys = [
        "platform_cut_percent",
        "driver_cut_percent",
        "business_owner_cut_percent",
        "referral_cut_percent",
    ]
    cfg = {k: float(PlatformConfig.get(k, 0)) for k in keys}
    total_pct = sum(cfg.values())
    if total_pct > 100.0:
        raise ValueError(f"Configured split percentages exceed 100%: {total_pct}%")
    return cfg


def calculate_split(total_amount: int, has_referral: bool, config: dict, metadata: dict | None = None) -> dict:
    """
    Returns split amounts in kobo. Uses integer math -- no floats for money.
    Supports order-based fee rules when metadata includes order inputs.
    """
    meta = metadata or {}

    if "items_total_kobo" in meta or "delivery_fee_kobo" in meta or meta.get("split_rule") == "order_v1":
        return order_v1_split(total_amount, has_referral, meta)

    return percent_split(total_amount, has_referral, config)


def order_v1_split(total_amount: int, has_referral: bool, meta: dict | None = None):
    meta = meta or {}
    items_total = int(meta.get("items_total_kobo") or 0)
    delivery_fee = int(meta.get("delivery_fee_kobo") or 0)

    fee_type = (meta.get("platform_fee_type") or "percent").lower().strip()
    fee_percent = float(meta.get("platform_fee_percent") or 5.0)
    fee_fixed = int(meta.get("platform_fee_fixed_kobo") or 500 * 100)

    if fee_type == "fixed":
        platform_policy = fee_fixed
    else:
        platform_policy = (items_total * _bps(fee_percent)) // 10_000

    expected_total = items_total + delivery_fee + platform_policy
    if total_amount:
        platform_effective = total_amount - items_total - delivery_fee
        if platform_effective < 0:
            raise ValueError(
                f"total_amount ({total_amount}) is less than items_total ({items_total}) + delivery_fee ({delivery_fee})"
            )
    else:
        platform_effective = platform_policy

    mismatch = (total_amount or expected_total) - expected_total
    if mismatch != 0:
        logger.info(
            "order_v1_split: total mismatch detected",
            extra={"expected_total": expected_total, "actual_total": total_amount, "mismatch": mismatch},
        )

    return {
        "policy": {
            "platform_fee_type": fee_type,
            "platform_fee_percent": fee_percent,
            "platform_fee_fixed_kobo": fee_fixed,
        },
        "inputs": {
            "items_total_kobo": items_total,
            "delivery_fee_kobo": delivery_fee,
            "expected_total_kobo": expected_total,
        },
        "amounts": {
            "platform": platform_effective,
            "driver": delivery_fee,
            "business_owner": items_total,
            "referral": 0,
        },
        "total": total_amount or expected_total,
        "has_referral": has_referral,
        "mismatch_kobo": expected_total - (total_amount or expected_total),
    }


def percent_split(total_amount: int, has_referral: bool, config: dict) -> dict:
    platform_pct = config["platform_cut_percent"]
    driver_pct = config["driver_cut_percent"]
    business_pct = config["business_owner_cut_percent"]
    referral_pct = config["referral_cut_percent"]

    if not has_referral:
        platform_pct += referral_pct
        referral_pct = 0

    driver_amt = (total_amount * _bps(driver_pct)) // 10_000
    business_amt = (total_amount * _bps(business_pct)) // 10_000
    referral_amt = (total_amount * _bps(referral_pct)) // 10_000
    platform_amt = total_amount - driver_amt - business_amt - referral_amt

    return {
        "percentages": {
            "platform": platform_pct,
            "driver": driver_pct,
            "business_owner": business_pct,
            "referral": referral_pct,
        },
        "amounts": {
            "platform": platform_amt,
            "driver": driver_amt,
            "business_owner": business_amt,
            "referral": referral_amt,
        },
        "total": total_amount,
        "has_referral": has_referral,
    }


def get_ledger_balance(user) -> int:
    from payments.models import LedgerEntry
    result = LedgerEntry.objects.filter(user=user).aggregate(total=Sum("amount"))
    return result["total"] or 0


@transaction.atomic
def credit_all_parties(sale, split: dict, picked_up: bool = False):
    """
    Credit all parties after service completion. All or nothing.
    Deadlock-free: locks Sale and involved User rows in deterministic order up front.
    Idempotent: exits early if credits have already been processed for this sale.
    """
    from django.contrib.auth import get_user_model
    from payments.models import LedgerEntry, Sale

    User = get_user_model()

    # Lock sale row to serialize concurrent settlement attempts
    sale = Sale.objects.select_for_update().get(pk=sale.pk)

    # Idempotency guard: if credits already exist, skip duplicate processing
    if LedgerEntry.objects.filter(sale=sale, type="credit").exists():
        logger.info("credit_all_parties: credits already recorded for sale %s, skipping", sale.reference)
        return

    parties = [
        {"user": sale.business_owner, "role": "business_owner", "amount": split["amounts"]["business_owner"]},
    ]
    if sale.driver is not None:
        parties.append({"user": sale.driver, "role": "driver", "amount": split["amounts"]["driver"]})
    else:
        if not picked_up and sale.payer and split["amounts"].get("driver", 0) > 0:
            parties.append({"user": sale.payer, "role": "customer", "amount": split["amounts"]["driver"]})

    if sale.referral_user and split["amounts"].get("referral", 0) > 0:
        parties.append({"user": sale.referral_user, "role": "referral", "amount": split["amounts"]["referral"]})

    # Filter out zero-amount parties
    parties = [p for p in parties if p["amount"] > 0 and p.get("user") is not None]

    # Deadlock prevention: sort all involved users by primary key and lock them up front
    user_ids = sorted({p["user"].id for p in parties})
    if user_ids:
        list(User.objects.select_for_update().filter(id__in=user_ids).order_by("id"))

    for party in parties:
        _create_ledger_entry(
            user=party["user"],
            sale=sale,
            role=party["role"],
            entry_type="credit",
            amount=party["amount"],
            notes=f"Credit for sale {sale.reference}",
        )


@transaction.atomic
def reverse_ledger_entries(sale, reason: str, responsible_party: str = "business"):
    """
    Reverse ledger entries depending on the responsible party:
    - 'business': Business fault -> reverse business owner credit (restaurant doesn't get paid).
    - 'driver': Driver fault -> driver credit is reversed/penalized, BUT business owner keeps their food earnings!
    - 'platform': Platform fault -> both business and driver keep their earnings (no credit reversal, platform absorbs cost).
    
    Deadlock-free & Idempotent: locks Sale and involved User rows in sorted order, skips already-reversed entries.
    """
    from django.contrib.auth import get_user_model
    from payments.models import LedgerEntry, Sale

    User = get_user_model()

    # Lock sale row to serialize concurrent reversal attempts
    sale = Sale.objects.select_for_update().get(pk=sale.pk)

    credits = list(LedgerEntry.objects.filter(sale=sale, type="credit"))

    to_reverse = []
    for entry in credits:
        # Prevent duplicate reversal if this role has already been reversed for this user on this sale
        if LedgerEntry.objects.filter(sale=sale, user=entry.user, role=entry.role, type="reversal").exists():
            continue

        should_reverse = False
        if responsible_party == "business":
            if entry.role in ("business_owner", "driver"):
                should_reverse = True
        elif responsible_party == "driver":
            if entry.role == "driver":
                should_reverse = True
        elif responsible_party == "platform":
            should_reverse = False
        else:
            should_reverse = True

        if should_reverse:
            to_reverse.append(entry)

    # Deadlock prevention: sort all involved users by primary key and lock them up front
    user_ids = sorted({entry.user_id for entry in to_reverse if entry.user_id})
    if user_ids:
        list(User.objects.select_for_update().filter(id__in=user_ids).order_by("id"))

    for entry in to_reverse:
        _create_ledger_entry(
            user=entry.user,
            sale=sale,
            role=entry.role,
            entry_type="reversal",
            amount=-abs(entry.amount),
            notes=f"Reversal ({responsible_party} fault): {reason}",
        )


@transaction.atomic
def _create_ledger_entry(user, sale, role, entry_type, amount, notes=""):
    """
    Atomically creates a LedgerEntry with monotonic seq, O(1) balance, and tamper-evident hash chaining.
    """
    from django.contrib.auth import get_user_model
    from payments.models import LedgerEntry

    User = get_user_model()
    # Lock user row to serialize chain creation and monotonic sequence
    User.objects.select_for_update().get(id=user.id)

    now = timezone.now()

    # Retrieve latest entry by monotonic sequence (avoids clock skew & UUID ordering issues)
    latest_entry = LedgerEntry.objects.filter(user=user).order_by("-seq").first()

    seq = (latest_entry.seq + 1) if latest_entry else 1
    prev_hash = latest_entry.row_hash if latest_entry else "GENESIS"
    # O(1) balance calculation under user lock
    balance_after = (latest_entry.balance_after if latest_entry else 0) + amount

    row_hash = LedgerEntry.generate_hash(
        sale_id=str(sale.id) if sale else "withdrawal",
        user_id=str(user.id),
        amount=amount,
        balance_after=balance_after,
        entry_type=entry_type,
        role=role,
        created_at=now.isoformat(),
        previous_hash=prev_hash,
        seq=seq,
        version=2,
    )

    return LedgerEntry.objects.create(
        user=user,
        sale=sale,
        role=role,
        type=entry_type,
        amount=amount,
        balance_after=balance_after,
        seq=seq,
        hash_version=2,
        previous_hash=prev_hash,
        row_hash=row_hash,
        notes=notes,
        created_at=now,
    )
