"""
split_calculator.py - handles split logic, ledger credits, row hashing
"""
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone


def load_split_config():
    from payments.models import PlatformConfig
    keys = [
        "platform_cut_percent",
        "driver_cut_percent",
        "business_owner_cut_percent",
        "referral_cut_percent",
    ]
    return {k: float(PlatformConfig.get(k, 0)) for k in keys}


def calculate_split(total_amount: int, has_referral: bool, config: dict, metadata: dict | None = None) -> dict:
    """
    Returns split amounts in kobo. Uses integer math -- no floats for money.
    Supports order-based fee rules when metadata includes order inputs.
    """
    meta = metadata or {}

    if "items_total_kobo" in meta or "delivery_fee_kobo" in meta or meta.get("split_rule") == "order_v1":
        return order_v1_split(total_amount, has_referral, meta)

    return percent_split(total_amount, has_referral, config)

def order_v1_split(total_amount: int, has_referral: bool, meta: dict = {}):
    items_total = int(meta.get("items_total_kobo") or 0)
    delivery_fee = int(meta.get("delivery_fee_kobo") or 0)

    fee_type = (meta.get("platform_fee_type") or "percent").lower().strip()
    fee_percent = float(meta.get("platform_fee_percent") or 5.0)
    fee_fixed = int(meta.get("platform_fee_fixed_kobo") or 500 * 100)

    if fee_type == "fixed":
        platform_policy = fee_fixed
    else:
        platform_policy = int(items_total * fee_percent / 100)

    expected_total = items_total + delivery_fee + platform_policy
    if total_amount:
        platform_effective = total_amount - items_total - delivery_fee
    else:
        platform_effective = platform_policy

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

def percent_split(total_amount: int, has_referral: bool, config: dict)->dict:
    platform_pct = config["platform_cut_percent"]
    driver_pct = config["driver_cut_percent"]
    business_pct = config["business_owner_cut_percent"]
    referral_pct = config["referral_cut_percent"]

    if not has_referral:
        platform_pct += referral_pct
        referral_pct = 0

    driver_amt = int(total_amount * driver_pct / 100)
    business_amt = int(total_amount * business_pct / 100)
    referral_amt = int(total_amount * referral_pct / 100)
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
def credit_all_parties(sale, split: dict):
    """Credit all parties after service completion. All or nothing."""
    parties = [
        {"user": sale.driver, "role": "driver", "amount": split["amounts"]["driver"]},
        {"user": sale.business_owner, "role": "business_owner", "amount": split["amounts"]["business_owner"]},
    ]
    if sale.referral_user and split["amounts"]["referral"] > 0:
        parties.append({"user": sale.referral_user, "role": "referral", "amount": split["amounts"]["referral"]})

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
def reverse_ledger_entries(sale, reason: str):
    """Reverse all credits for a sale. Inserts reversals -- never deletes originals."""
    from payments.models import LedgerEntry
    for entry in LedgerEntry.objects.filter(sale=sale, type="credit"):
        _create_ledger_entry(
            user=entry.user,
            sale=sale,
            role=entry.role,
            entry_type="reversal",
            amount=-abs(entry.amount),
            notes=f"Reversal: {reason}",
        )


def _create_ledger_entry(user, sale, role, entry_type, amount, notes=""):
    from payments.models import LedgerEntry
    now = timezone.now()
    balance_after = get_ledger_balance(user) + amount
    row_hash = LedgerEntry.generate_hash(
        sale_id=str(sale.id) if sale else "withdrawal",
        user_id=str(user.id),
        amount=amount,
        entry_type=entry_type,
        role=role,
        created_at=now.isoformat(),
    )
    return LedgerEntry.objects.create(
        user=user,
        sale=sale,
        role=role,
        type=entry_type,
        amount=amount,
        balance_after=balance_after,
        row_hash=row_hash,
        notes=notes,
        created_at=now,
    )
