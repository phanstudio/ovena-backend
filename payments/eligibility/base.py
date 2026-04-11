from __future__ import annotations

from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from payments.models import Withdrawal
# from payments.models import UserAccount
from payments.services.split_calculator import get_ledger_balance

# These are read from services.py to stay DRY
from payments.payouts.helper import (
    _pending_total,
    _normalize_ledger_role,
)
from payments.payouts.constants import (
    DAILY_WITHDRAWAL_LIMIT_AMOUNT,
    DAILY_WITHDRAWAL_LIMIT_COUNT,
    WITHDRAWAL_COOLDOWN_HOURS,
    MINIMUM_BY_ROLE
)
from payments.payouts.bridge import resolve_payout_account
from dataclasses import dataclass


@dataclass
class WithdrawalDecision:
    eligible: bool
    checks: dict
    minimum_amount_kobo: int
    available_balance_kobo: int


# ---------------------------------------------------------------------------
# Base evaluator
# ---------------------------------------------------------------------------

class WithdrawalEligibilityEvaluator:
    """
    Base eligibility evaluator. Performs all shared checks:
      - recipient ready
      - minimum amount
      - sufficient balance
      - cooldown
      - daily count
      - daily amount

    Subclasses call super().evaluate() and then layer on role-specific logic.
    """

    role: str  # must be set by subclass __init__

    def __init__(self, user, amount_kobo: int, role: str):
        self.user = user
        self.amount_kobo = amount_kobo
        self.role = _normalize_ledger_role(role)
        self.now = timezone.now()

    # ------------------------------------------------------------------
    # Overridable data accessors
    # ------------------------------------------------------------------

    def get_balance(self) -> int:
        return get_ledger_balance(self.user)

    def get_pending(self) -> int:
        return _pending_total(self.user)

    def get_payout_account(self):
        """
        Resolve the concrete payout account for this actor.
        Subclasses override to point at the right model.
        Default: UserAccount (individuals).
        """
        return resolve_payout_account(self.user, self.role)

    def get_minimum(self) -> int:
        return MINIMUM_BY_ROLE.get(self.role, 0)

    # ------------------------------------------------------------------
    # Individual check methods (overridable)
    # ------------------------------------------------------------------

    def check_recipient_ready(self, account) -> bool:
        return bool(account and account.get_recipient_code())

    def check_cooldown(self) -> bool:
        last = (
            Withdrawal.objects
            .filter(user=self.user, status="complete")
            .order_by("-completed_at")
            .first()
        )
        if not last or not last.completed_at:
            return True
        return (self.now - last.completed_at) >= timedelta(hours=WITHDRAWAL_COOLDOWN_HOURS)

    def check_daily_limits(self):
        today_start = self.now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_qs = Withdrawal.objects.filter(
            user=self.user,
            status__in=["pending_batch", "processing", "complete"],
            requested_at__gte=today_start,
        )
        count = today_qs.count()
        amount = today_qs.aggregate(total=Sum("amount"))["total"] or 0
        return (
            count < DAILY_WITHDRAWAL_LIMIT_COUNT,
            amount + self.amount_kobo <= DAILY_WITHDRAWAL_LIMIT_AMOUNT,
        )

    # ------------------------------------------------------------------
    # Core evaluate — subclasses call super() then extend checks dict
    # ------------------------------------------------------------------

    def evaluate(self) -> WithdrawalDecision:
        balance = self.get_balance()
        pending = self.get_pending()
        available = balance - pending
        minimum = self.get_minimum()
        account = self.get_payout_account()

        daily_count_ok, daily_amount_ok = self.check_daily_limits()

        checks = {
            "recipient_ready": self.check_recipient_ready(account),
            "role_eligible": self.role in MINIMUM_BY_ROLE,
            "minimum_amount": self.amount_kobo >= minimum,
            "sufficient_balance": available >= self.amount_kobo,
            "cooldown_ok": self.check_cooldown(),
            "daily_count_ok": daily_count_ok,
            "daily_amount_ok": daily_amount_ok,
        }

        return WithdrawalDecision(
            eligible=all(checks.values()),
            checks=checks,
            minimum_amount_kobo=minimum,
            available_balance_kobo=available,
        )


# ---------------------------------------------------------------------------
# Business evaluator
# ---------------------------------------------------------------------------

class BusinessWithdrawalEvaluator(WithdrawalEligibilityEvaluator):
    """
    Eligibility evaluator for business_owner role.

    Resolves the payout account from BusinessPayoutAccount (via business
    entity) rather than UserAccount. Adds a check that the business has
    completed KYC onboarding before any withdrawal is allowed.
    """

    def __init__(self, user, amount_kobo: int):
        super().__init__(user, amount_kobo, role="business_owner")

    def get_payout_account(self):
        # Bridge resolves BusinessPayoutAccount for this role
        return resolve_payout_account(self.user, self.role)

    def _check_kyc_complete(self) -> bool:
        try:
            admin = self.user.business_admin
            status = admin.cerd  # BusinessOnboardStatus
            return status.is_onboarding_complete
        except Exception:
            # If onboarding model doesn't exist yet, don't hard-block —
            # fail open here and tighten once onboarding is enforced.
            return True

    def evaluate(self) -> WithdrawalDecision:
        decision = super().evaluate()

        extra = {
            "kyc_complete": self._check_kyc_complete(),
        }

        merged_checks = {**decision.checks, **extra}
        return WithdrawalDecision(
            eligible=all(merged_checks.values()),
            checks=merged_checks,
            minimum_amount_kobo=decision.minimum_amount_kobo,
            available_balance_kobo=decision.available_balance_kobo,
        )


# ---------------------------------------------------------------------------
# Driver evaluator
# ---------------------------------------------------------------------------

class DriverWithdrawalEvaluator(WithdrawalEligibilityEvaluator):
    """
    Eligibility evaluator for driver role.

    Resolves payout account from UserAccount (personal account).
    Hook point for future driver-specific checks: active ride lock,
    vehicle document status, suspension flags, etc.
    """

    def __init__(self, user, amount_kobo: int):
        super().__init__(user, amount_kobo, role="driver")

    def get_payout_account(self):
        return resolve_payout_account(self.user, self.role)

    def _check_driver_active(self) -> bool:
        """
        Guard: don't allow withdrawal if driver profile is suspended.
        Extend this as driver lifecycle states expand.
        """
        try:
            profile = self.user.driver_profile
            return not getattr(profile, "suspended", False)
        except Exception:
            return True

    def evaluate(self) -> WithdrawalDecision:
        decision = super().evaluate()

        extra = {
            "driver_active": self._check_driver_active(),
        }

        merged_checks = {**decision.checks, **extra}
        return WithdrawalDecision(
            eligible=all(merged_checks.values()),
            checks=merged_checks,
            minimum_amount_kobo=decision.minimum_amount_kobo,
            available_balance_kobo=decision.available_balance_kobo,
        )


# ---------------------------------------------------------------------------
# Referral evaluator (thin — no extra checks yet)
# ---------------------------------------------------------------------------

class ReferralWithdrawalEvaluator(WithdrawalEligibilityEvaluator):
    def __init__(self, user, amount_kobo: int):
        super().__init__(user, amount_kobo, role="referral")

    def get_payout_account(self):
        return resolve_payout_account(self.user, self.role)


# ---------------------------------------------------------------------------
# Dispatcher — replaces the old standalone evaluate_eligibility()
# ---------------------------------------------------------------------------

_EVALUATOR_MAP = {
    "business_owner": BusinessWithdrawalEvaluator,
    "driver": DriverWithdrawalEvaluator,
    "referral": ReferralWithdrawalEvaluator,
}


def evaluate_eligibility(user, amount_kobo: int, role: str | None = None) -> WithdrawalDecision:
    """
    Public entry point. Resolves the right evaluator by role and delegates.
    Backward-compatible replacement for the old standalone function.
    """
    from payments.payouts.services import _infer_ledger_role_for_user

    resolved_role = _normalize_ledger_role(role) or _infer_ledger_role_for_user(user)
    evaluator_cls = _EVALUATOR_MAP.get(resolved_role)

    if evaluator_cls is None:
        return WithdrawalDecision(
            eligible=False,
            checks={"role_eligible": False},
            minimum_amount_kobo=0,
            available_balance_kobo=0,
        )

    return evaluator_cls(user=user, amount_kobo=amount_kobo).evaluate()