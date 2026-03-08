from __future__ import annotations

from datetime import date

from django.db.models import Q

from payments.integrations.paystack.client import PaystackClient
from payments.models import ReconciliationLog, Withdrawal


SEVERITY_BY_ISSUE = {
    "amount_mismatch": "high",
    "recipient_mismatch": "critical",
    "status_mismatch": "critical",
    "provider_fetch_error": "high",
}


def _severity(issue: str) -> str:
    return SEVERITY_BY_ISSUE.get(issue, "medium")


def _local_vs_provider_status(local_status: str, provider_status: str) -> bool:
    normalized = (provider_status or "").lower().strip()
    if local_status == "complete":
        return normalized == "success"
    if local_status == "failed":
        return normalized in {"failed", "reversed"}
    if local_status == "processing":
        return normalized in {"pending", "otp", "processing", "queued"}
    return True


def _collect_candidates(run_date: date):
    return Withdrawal.objects.select_related("user").filter(
        Q(batch_date=run_date)
        | Q(strategy=Withdrawal.STRATEGY_REALTIME, processed_at__date=run_date)
    ).exclude(paystack_transfer_code="")


def run_reconciliation(*, run_date: date, alert_callback=None) -> dict:
    paystack_client = PaystackClient()
    mismatches: list[dict] = []
    checked = 0

    for withdrawal in _collect_candidates(run_date):
        try:
            ps = paystack_client.fetch_transfer(withdrawal.paystack_transfer_code).get("data", {})
            checked += 1
        except Exception as exc:
            mismatches.append(
                {
                    "severity": _severity("provider_fetch_error"),
                    "issue": "provider_fetch_error",
                    "withdrawal_id": str(withdrawal.id),
                    "user_id": str(withdrawal.user_id),
                    "error": str(exc),
                }
            )
            continue

        if ps.get("amount") != withdrawal.amount:
            mismatches.append(
                {
                    "severity": _severity("amount_mismatch"),
                    "issue": "amount_mismatch",
                    "withdrawal_id": str(withdrawal.id),
                    "user_id": str(withdrawal.user_id),
                    "local_amount": withdrawal.amount,
                    "paystack_amount": ps.get("amount"),
                }
            )

        ps_recipient = ps.get("recipient", {}).get("recipient_code", "")
        if ps_recipient != withdrawal.paystack_recipient_code:
            mismatches.append(
                {
                    "severity": _severity("recipient_mismatch"),
                    "issue": "recipient_mismatch",
                    "withdrawal_id": str(withdrawal.id),
                    "user_id": str(withdrawal.user_id),
                    "local_recipient": withdrawal.paystack_recipient_code,
                    "paystack_recipient": ps_recipient,
                }
            )

        ps_status = ps.get("status", "")
        if not _local_vs_provider_status(withdrawal.status, ps_status):
            mismatches.append(
                {
                    "severity": _severity("status_mismatch"),
                    "issue": "status_mismatch",
                    "withdrawal_id": str(withdrawal.id),
                    "user_id": str(withdrawal.user_id),
                    "local_status": withdrawal.status,
                    "paystack_status": ps_status,
                }
            )

    status = "clean" if not mismatches else "mismatches_found"
    log = ReconciliationLog.objects.create(
        run_date=run_date,
        status=status,
        total_checked=checked,
        mismatches=len(mismatches),
        mismatch_details=mismatches,
    )

    summary = {
        "run_date": str(run_date),
        "status": status,
        "checked": checked,
        "mismatches": len(mismatches),
        "log_id": str(log.id),
    }

    if mismatches and alert_callback:
        alert_callback(summary, mismatches)

    return summary
