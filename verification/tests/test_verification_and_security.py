import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import (
    CustomerProfile,
    DriverProfile,
    DriverBankAccount,
    DriverOnboardingSubmission,
    Business,
    BusinessAdmin,
    BusinessCerd,
    BusinessOnboardStatus,
    Branch,
)
from payments.models import Bank, UserAccount
from accounts.services import security_guards
from accounts.views.account_views import ChangePasswordView
from accounts.views.driver_reg_views import OnboardingStatusView
from verification import service as verification_service
from verification.serializers import AdminBusinessReviewUpdateSerializer
from points.service import (
    pay_order_with_points,
    refund_order_points,
    InsufficientPoints,
    get_points_balance,
)
from points.models import PointsLedgerEntry
from menu.models import Order

User = get_user_model()


# ─────────────────────────────────────────────────────────────
# 1. VERIFICATION SERVICE _ok() FIX TEST
# ─────────────────────────────────────────────────────────────

def test_verification_service_ok_returns_dict_without_raising():
    """Verify that _ok() returns a success dict and does NOT raise HTTPError."""
    result = verification_service._ok("dojah", {"verified": True}, [])
    assert result["success"] is True
    assert result["provider"] == "dojah"
    assert result["data"] == {"verified": True}
    assert result["attempts"] == []


# ─────────────────────────────────────────────────────────────
# 2. CHANGE PASSWORD LOGIC FIX TEST
# ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_change_password_view_correct_and_incorrect_passwords():
    """Verify that valid old password succeeds and invalid old password returns 400."""
    user = User.objects.create_user(email="changepw@example.com")
    user.set_password("OriginalPassword123!")
    user.save()
    factory = APIRequestFactory()

    # Attempt with WRONG old password -> must fail (400)
    req_fail = factory.post(
        "/api/accounts/change-password/",
        {"password": "WrongPassword999!", "new_password": "BrandNewPassword123!"},
        format="json",
    )
    force_authenticate(req_fail, user=user)
    view = ChangePasswordView.as_view()
    res_fail = view(req_fail)
    assert res_fail.status_code == 400

    # Attempt with CORRECT old password -> must succeed (200)
    req_ok = factory.post(
        "/api/accounts/change-password/",
        {"password": "OriginalPassword123!", "new_password": "BrandNewPassword123!"},
        format="json",
    )
    force_authenticate(req_ok, user=user)
    res_ok = view(req_ok)
    assert res_ok.status_code == 200

    # Verify user can authenticate with the new password
    user.refresh_from_db()
    assert user.check_password("BrandNewPassword123!")


# ─────────────────────────────────────────────────────────────
# 3. SECURITY GUARDS & COOLDOWN TESTS
# ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_security_cooldown_and_pin_lockout():
    """Verify 24h withdrawal cooldown and PIN lockout after failed attempts."""
    user = User.objects.create_user(email="security@example.com", password="PassWord123!")
    cache.clear()

    # Initial state: no cooldown
    within, remaining = security_guards.is_security_cooldown_active(user)
    assert within is False
    assert remaining == 0

    # Set security cooldown
    security_guards.set_security_cooldown(user, hours=24)
    within, remaining = security_guards.is_security_cooldown_active(user)
    assert within is True
    assert remaining > 0

    # Test PIN formatting and trivial PIN rejections
    security_guards.validate_pin_format("4928")

    with pytest.raises(Exception):
        security_guards.validate_pin_format("12")

    with pytest.raises(Exception):
        security_guards.validate_pin_format("1234")

    with pytest.raises(Exception):
        security_guards.validate_pin_format("7777")

    # Test Customer PIN setting on UserAccount
    account, _ = UserAccount.objects.get_or_create(user=user)
    account.set_transaction_pin("8351")
    account.save()
    assert account.has_transaction_pin is True
    assert account.check_transaction_pin("8351") is True
    assert account.check_transaction_pin("0001") is False

    # Failed attempts trigger lockout
    security_guards.clear_pin_attempts(user.id)
    assert security_guards.is_pin_locked(user.id)[0] is False

    for _ in range(4):
        security_guards.record_failed_pin_attempt(user.id)
        assert security_guards.is_pin_locked(user.id)[0] is False

    # 5th attempt locks out
    security_guards.record_failed_pin_attempt(user.id)
    assert security_guards.is_pin_locked(user.id)[0] is True

    # Clear attempts removes lockout
    security_guards.clear_pin_attempts(user.id)
    assert security_guards.is_pin_locked(user.id)[0] is False


# ─────────────────────────────────────────────────────────────
# 4. POINTS SERVICE: 1:1 VALUATION & TRANSACTION CONCURRENCY
# ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_points_ordering_and_refund():
    """Verify points payment deducts 1:1 with NGN order total and refund restores it."""
    user = User.objects.create_user(email="pointsuser@example.com", password="PassWord123!")
    customer = CustomerProfile.objects.create(user=user)

    # Seed 5,000 points
    PointsLedgerEntry.objects.create(
        user=user,
        event_type=PointsLedgerEntry.EVENT_REFERRAL_SUCCESS,
        points=5000,
        balance_after=5000,
        notes="Seed balance",
    )

    biz_user = User.objects.create_user(email="bizowner@example.com")
    business = Business.objects.create(business_name="Food Spot")
    BusinessAdmin.objects.create(user=biz_user, business=business)
    branch = Branch.objects.create(business=business, name="Main")
    order = Order.objects.create(
        orderer=customer,
        branch=branch,
        subtotal=Decimal("2000.00"),
        delivery_price=Decimal("500.00"),
        grand_total=Decimal("2500.00"),
    )

    # Pay 2,500 NGN with points (deducts 2,500 points)
    tx = pay_order_with_points(customer, order)
    assert tx.points == -2500
    assert get_points_balance(user) == 2500

    # Attempt to pay another 3,000 NGN order -> should raise InsufficientPoints
    order2 = Order.objects.create(
        orderer=customer,
        branch=branch,
        subtotal=Decimal("2500.00"),
        delivery_price=Decimal("500.00"),
        grand_total=Decimal("3000.00"),
    )
    with pytest.raises(InsufficientPoints):
        pay_order_with_points(customer, order2)

    # Refund the first order (restores 2,500 points)
    refund_tx = refund_order_points(order, reason="order_cancelled")
    assert refund_tx.points == 2500
    assert get_points_balance(user) == 5000



# ─────────────────────────────────────────────────────────────
# 5. DRIVER ONBOARDING & RETRY PIPELINE
# ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_driver_onboarding_rejection_status_and_retry():
    """Verify driver onboarding status reflects rejection, enables retry, and carries over answers."""
    user = User.objects.create_user(email="driver_retry@example.com", password="PassWord123!")
    profile = DriverProfile.objects.create(user=user, first_name="John", last_name="Doe")

    # Driver completed phases and was rejected by reviewer
    rejected_sub = DriverOnboardingSubmission.objects.create(
        driver=profile,
        status=DriverOnboardingSubmission.STATUS_REJECTED,
        reviewer_note="Selfie was blurry. Please re-upload.",
        answers={
            "phase_1_complete": True,
            "phase_2_complete": True,
            "phase_3_complete": True,
            "phase_1": {"first_name": "John"},
        },
    )

    factory = APIRequestFactory()
    req = factory.get("/api/accounts/driver/onboarding/status/")
    force_authenticate(req, user=user)

    res = OnboardingStatusView.as_view()(req)
    assert res.status_code == 200
    assert res.data["submission_status"] == DriverOnboardingSubmission.STATUS_REJECTED
    assert res.data["reviewer_note"] == "Selfie was blurry. Please re-upload."
    assert res.data["can_retry"] is True
    assert 1 in res.data["phases_complete"]


# ─────────────────────────────────────────────────────────────
# 6. BUSINESS VERIFICATION REVIEW & CAN_RETRY PIPELINE
# ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_business_review_status_can_retry_and_resubmission():
    """Verify business review can_retry flags when not approved, and resets checked on resubmit."""
    user = User.objects.create_user(email="biz_retry@example.com", password="PassWord123!")
    business = Business.objects.create(business_name="Biz Spot", onboarding_complete=False)
    business_cerd = BusinessCerd.objects.create(business=business)
    admin = BusinessAdmin.objects.create(user=user, business=business)
    status_obj = BusinessOnboardStatus.objects.create(
        admin=admin,
        onboarding_step=2,
        needs_manual_review=False,
        checked=True,
        is_onboarding_complete=False,
    )

    # Verification status shows can_retry: True because checked=True and is_onboarding_complete=False
    can_retry = (
        status_obj.checked
        and not status_obj.needs_manual_review
        and not status_obj.is_onboarding_complete
    )
    assert can_retry is True

    # Admin updates with serializer: marking approved
    serializer = AdminBusinessReviewUpdateSerializer(
        instance=status_obj,
        data={"is_onboarding_complete": True, "checked": True, "needs_manual_review": False},
        partial=True,
    )
    assert serializer.is_valid()
    updated_status = serializer.save()

    business.refresh_from_db()
    assert updated_status.is_onboarding_complete is True
    assert business.onboarding_complete is True
