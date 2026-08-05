"""
sale_service.py - initialize payment, complete service, process refund
"""
import uuid

from django.db import transaction
from django.utils import timezone
from payments.models import Sale, User
from payments.services.split_calculator import calculate_split, credit_all_parties, load_split_config
from payments.integrations.paystack.client import PaystackClient
from referrals.services import referred_by
from payments.services.sale_extention import *


paystack_client = PaystackClient()

@transaction.atomic
def initialize_sale(payer_id, driver_id, business_owner_id, amount_kobo, metadata=None):
    """
    STEP 1: User is about to pay.
    Creates Paystack payment link + pending Sale record.
    Returns payment URL to redirect the user to.
    """
    payer = User.objects.get(id=payer_id)
    driver = User.objects.get(id=driver_id) if driver_id else None
    business_owner = User.objects.get(id=business_owner_id)
    referral = referred_by(payer)
    referral_user = referral.referrer_profile.user if referral else None

    config = load_split_config() #remove
    split = calculate_split(amount_kobo, bool(referral_user), config, metadata=metadata or {})

    sale_ref = f"SALE_{uuid.uuid4().hex[:12].upper()}"

    payload = {
        "email": payer.email,
        "amount": amount_kobo,
        "reference": sale_ref,
        "metadata": {
            "sale_reference": sale_ref,
            "driver_id": str(driver.id) if driver else None,
            "business_owner_id": str(business_owner.id),
            "referral_user_id": str(referral_user.id) if referral_user else None,
            "split_breakdown": split,
            **(metadata or {}),
        },
        "callback_url": "https://ovena-backend-production.up.railway.app/api/payments/paystack/callback/",
    }
    data = paystack_client.initialize_transaction(payload).get("data", {})

    metadata_snapshot = {
        **(metadata or {}),
        "split_inputs": split.get("inputs", {}),
        "split_policy": split.get("policy", {}),
        "split_amounts": split.get("amounts", {}),
        "split_total_kobo": split.get("total"),
        "split_has_referral": split.get("has_referral"),
        "split_mismatch_kobo": split.get("mismatch_kobo", 0),
    }

    sale = Sale.objects.create(
        reference=sale_ref,
        paystack_reference=data.get("reference", sale_ref),
        paystack_access_code=data.get("access_code", ""),
        payer=payer,
        driver=driver,
        business_owner=business_owner,
        referral_user=referral_user,
        total_amount=amount_kobo,
        status="pending",
        split_snapshot=split,
        metadata=metadata_snapshot,
    )

    return {
        "sale_id": str(sale.id),
        "reference": sale_ref,
        "payment_url": data.get("authorization_url", ""),
        "amount_ngn": amount_kobo / 100,
        "split_preview": {k: f"NGN {v/100:.2f}" for k, v in split["amounts"].items()},
    }

def assign_driver(order, driver_id):
    Sale.objects.filter(id=order.sale_id).update(driver_id=driver_id)

@transaction.atomic
def complete_service(sale_id, picked_up: bool= False):
    """
    STEP 2: Service is done. Credit all parties from the frozen split snapshot.
    """
    sale = Sale.objects.select_for_update().get(id=sale_id)

    if sale.status != "in_escrow":
        raise ValueError(f"Cannot complete sale with status: {sale.status}")

    split = sale.split_snapshot
    credit_all_parties(sale, split, picked_up)

    sale.status = "completed"
    sale.service_completed_at = timezone.now()
    sale.save()

    return {
        "success": True,
        "sale_reference": sale.reference,
        "credits_issued": {k: v / 100 for k, v in split["amounts"].items()},
    }
