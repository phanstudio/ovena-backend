from __future__ import annotations

import logging
from django.utils import timezone
from payments.models import Withdrawal, LedgerEntry
from accounts.services.security_guards import set_security_cooldown

logger = logging.getLogger(__name__)


def verify_user_ledger_chain_since_last_withdrawal(user) -> tuple[bool, str, list[str]]:
    """
    Verifies hash integrity and chain continuity of a user's ledger entries since their latest completed withdrawal.
    Returns (is_valid, reason, failed_entry_ids).
    """
    last_withdrawal = (
        Withdrawal.objects.filter(user=user, status="complete")
        .order_by("-completed_at", "-requested_at")
        .first()
    )

    all_user_entries = LedgerEntry.objects.filter(user=user).order_by("seq")

    if last_withdrawal:
        since_time = last_withdrawal.completed_at or last_withdrawal.requested_at
        if since_time:
            # Baseline hash comes from the last entry at or before since_time
            prior_entry = all_user_entries.filter(created_at__lte=since_time).last()
            prev_expected_hash = prior_entry.row_hash if prior_entry else "GENESIS"
            entries = all_user_entries.filter(created_at__gt=since_time)
        else:
            prev_expected_hash = "GENESIS"
            entries = all_user_entries
    else:
        prev_expected_hash = "GENESIS"
        entries = all_user_entries

    failed_ids = []
    for entry in entries:
        try:
            if not entry.verify_hash():
                failed_ids.append(str(entry.id))
            elif entry.previous_hash != prev_expected_hash:
                logger.error(
                    "Ledger entry %s chain broken: expected previous_hash %s, got %s",
                    entry.id, prev_expected_hash, entry.previous_hash
                )
                failed_ids.append(str(entry.id))
        except Exception as exc:
            logger.error("Ledger entry %s hash verification raised error: %s", entry.id, exc)
            failed_ids.append(str(entry.id))
        prev_expected_hash = entry.row_hash

    if failed_ids:
        reason = f"Hash mismatch detected on {len(failed_ids)} ledger row(s): {', '.join(failed_ids[:5])}"
        logger.warning(
            "payments.ledger.tampering_detected",
            extra={"user_id": str(user.id), "failed_entry_ids": failed_ids},
        )
        return False, reason, failed_ids

    return True, "Hash chain intact", []


def flag_withdrawal(withdrawal: Withdrawal, reason: str, failed_entry_ids: list[str] | None = None) -> Withdrawal:
    """
    Quarantines a withdrawal, flags it on the database, alerts admin via a high-priority
    support ticket, applies a security cooldown on the user, and sends a compliance notice.
    """
    withdrawal.is_flagged = True
    withdrawal.flag_reason = reason
    withdrawal.flagged_at = timezone.now()
    withdrawal.save(update_fields=["is_flagged", "flag_reason", "flagged_at"])

    # 1. Freeze user withdrawals
    set_security_cooldown(
        withdrawal.user,
        hours=72,
        reason=f"Withdrawal compliance flag: {reason}",
    )

    # 2. Dispatch high-priority support ticket
    try:
        from support_center.task import create_system_ticket

        create_system_ticket(
            user=withdrawal.user,
            role="customer",
            subject=f"[SECURITY] Withdrawal Ledger Tampering Flagged ({withdrawal.id})",
            message=(
                f"Withdrawal {withdrawal.id} for user {withdrawal.user_id} was flagged.\n"
                f"Reason: {reason}\n"
                f"Failed Row IDs: {failed_entry_ids or []}"
            ),
            category="security",
        )
    except Exception as exc:
        logger.warning("Failed to auto-create security support ticket: %s", exc)

    # 3. Dispatch user notification email
    try:
        from common.mail.services import send_security_alert_email

        if getattr(withdrawal.user, "email", None):
            send_security_alert_email(
                email=withdrawal.user.email,
                alert_type="withdrawal_flagged",
                message="Your recent withdrawal request was flagged for compliance review. Payouts are temporarily held while our team reviews the claim.",
                name=getattr(withdrawal.user, "first_name", None),
            )
    except Exception as exc:
        logger.warning("Failed to dispatch security alert email: %s", exc)

    return withdrawal
