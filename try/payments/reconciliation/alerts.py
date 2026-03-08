import logging
from typing import Any

logger = logging.getLogger(__name__)


def send_reconciliation_alert(summary: dict[str, Any], mismatches: list[dict[str, Any]]) -> None:
    """
    Adapter hook for external notifications (Slack/email/webhook).
    Replace logger call with your notifier integration.
    """
    logger.error("[RECONCILE ALERT] summary=%s mismatches=%s", summary, mismatches)
