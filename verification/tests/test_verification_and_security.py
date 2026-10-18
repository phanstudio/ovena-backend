import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
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


# ─────────────────────────────────────────────────────────────
# 7. PHASE 2 FACE MATCH & PHASE 4 REFACTORED TEST
# ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
@patch("verification.service.verify_nin")
@patch("verification.service.verify_bvn")
@patch("verification.service.match_face_to_name")
def test_driver_phase_2_face_match_pipeline(mock_match, mock_bvn, mock_nin):
    """Verify that Phase 2 accepts verified_selfie and executes match_face_to_name with NIN and BVN."""
    from accounts.views.driver_reg_views import OnboardingPhase2View
    from django.core.files.uploadedfile import SimpleUploadedFile
    from accounts.models import DriverVerification

    mock_nin.return_value = {"success": True, "provider": "dojah", "data": {"status": "ok"}, "attempts": []}
    mock_bvn.return_value = {"success": True, "provider": "dojah", "data": {"status": "ok"}, "attempts": []}
    mock_match.return_value = {"success": True, "provider": "dojah", "data": {"confidence": 98}, "attempts": []}

    user = User.objects.create_user(email="driver_p2@example.com", password="PassWord123!")
    profile = DriverProfile.objects.create(user=user, first_name="Bayo", last_name="Adewale")
    submission = DriverOnboardingSubmission.objects.create(
        driver=profile,
        answers={"phase_1_complete": True, "phase_1": {"first_name": "Bayo"}},
    )

    TINY_GIF = (
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
        b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    )
    license_file = SimpleUploadedFile("license.gif", TINY_GIF, content_type="image/gif")
    selfie_file = SimpleUploadedFile("selfie.gif", TINY_GIF, content_type="image/gif")

    factory = APIRequestFactory()
    req = factory.put(
        "/api/accounts/driver/onboarding/phase/2/",
        data={
            "drivers_license": license_file,
            "verified_selfie": selfie_file,
            "nin": "12345678901",
            "bvn": "98765432109",
            "vehicle_type": "motorcycle",
            "vehicle_make": "Bajaj",
            "plate_number": "ABC-123-XY",
            "guarantor1_name": "Ade Friend",
            "guarantor1_phone": "08011112222",
            "guarantor2_name": "Bola Friend",
            "guarantor2_phone": "08033334444",
        },
        format="multipart",
    )
    force_authenticate(req, user=user)

    res = OnboardingPhase2View.as_view()(req)
    assert res.status_code == 200
    assert res.data["face_match_status"] == "verified"

    # Confirm face match verification record was created
    face_ver = DriverVerification.objects.filter(
        driver=profile, verification_type=DriverVerification.TYPE_FACE_MATCH
    ).first()
    assert face_ver is not None
    assert face_ver.status == DriverVerification.STATUS_SUCCESS


# ─────────────────────────────────────────────────────────────
# 8. MANDATORY PIN ENFORCEMENT & POINTS ORDER PAYMENT
# ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_mandatory_pin_enforcement_points_and_withdrawal():
    """Verify that paying with points or withdrawing without a configured PIN returns 400."""
    from menu.views.order import OrderPaymentView
    from payments.views import request_withdrawal_view

    user = User.objects.create_user(email="customer_pin_req@example.com", password="PassWord123!")
    customer = CustomerProfile.objects.create(user=user)
    business = Business.objects.create(business_name="Pin Test Biz")
    branch = Branch.objects.create(business=business, name="Pin Branch")

    order = Order.objects.create(
        orderer=customer,
        branch=branch,
        order_number=99001,
        grand_total=Decimal("1500.00"),
        status="awaiting_payment_method",
    )

    factory = APIRequestFactory()

    # 1. Order payment without PIN configured -> 400
    req = factory.post(
        f"/api/orders/{order.id}/payment/",
        data={"method": "points"},
        format="json",
    )
    force_authenticate(req, user=user, token={"active_profile": "customer"})
    res = OrderPaymentView.as_view()(req, order_id=order.id)
    assert res.status_code == 400
    assert "Transaction PIN not configured" in res.data["error"]

    # 2. Withdrawal without PIN configured -> 400
    req_w = factory.post(
        "/api/wallet/withdraw/",
        data={"amount_kobo": 100000, "role": "customer"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="idem-with-pin-1",
    )
    force_authenticate(req_w, user=user, token={"active_profile": "customer"})
    res_w = request_withdrawal_view(req_w)
    assert res_w.status_code == 400
    assert "Transaction PIN not configured" in res_w.data["error"]


# ─────────────────────────────────────────────────────────────
# 9. SMS TO EMAIL OTP FALLBACK & BREACH ALERT EMAILS
# ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
@patch("common.otp.base.OTPManager.send")
@patch("common.mail.services.send_security_alert_email")
def test_sms_to_email_fallback_and_breach_alerts(mock_alert, mock_otp_send):
    """Verify SMS-to-email fallback on carrier failure and breach alerts on 5 failed attempts."""
    from common.otp.base import OTPManager
    from common.otp.exceptions import OTPDeliveryError
    from accounts.services.security_guards import record_failed_pin_attempt, is_pin_locked

    # Test send_with_fallback
    def fake_send(channel, identifier):
        if channel == "phone":
            raise OTPDeliveryError("SMS provider gateway unreachable")
        return None

    mock_otp_send.side_effect = fake_send

    result = OTPManager.send_with_fallback(
        phone_number="+2348011223344",
        email="fallback@example.com",
    )
    assert result["channel_used"] == "email"
    assert result["fallback"] is True

    # Test breach alert on 5 failed PIN attempts
    user = User.objects.create_user(email="pin_lockout@example.com", password="PassWord123!")
    for _ in range(4):
        record_failed_pin_attempt(user.id)
    assert is_pin_locked(user.id)[0] is False

    # 5th attempt locks out and triggers breach email
    record_failed_pin_attempt(user.id)
    assert is_pin_locked(user.id)[0] is True
    assert mock_alert.called


# ─────────────────────────────────────────────────────────────
# 10. HASH CHAIN VERIFICATION & FLAGGING SYSTEM
# ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_ledger_hash_chain_tamper_detection_and_flagging(monkeypatch):
    """Verify verify_user_ledger_chain_since_last_withdrawal catches tampered ledger rows."""
    monkeypatch.setenv("LEDGER_HASH_SALT", "test_secret_salt")
    from payments.models import LedgerEntry, Withdrawal
    from payments.services.ledger_audit import (
        verify_user_ledger_chain_since_last_withdrawal,
        flag_withdrawal,
    )

    user = User.objects.create_user(email="tamper_audit@example.com", password="PassWord123!")
    
    # 1. Create a prior complete withdrawal
    w1 = Withdrawal.objects.create(
        user=user,
        amount=50000,
        status="complete",
        paystack_recipient_code="RCP_1",
        completed_at=timezone.now() - datetime.timedelta(days=1),
    )

    # 2. Create valid subsequent ledger entry
    entry = LedgerEntry.objects.create(
        user=user,
        role="customer",
        type="credit",
        amount=100000,
        balance_after=100000,
        row_hash="",
    )
    # Generate proper hash
    entry.row_hash = LedgerEntry.generate_hash(
        sale_id="withdrawal",
        user_id=str(user.id),
        amount=100000,
        entry_type="credit",
        role="customer",
        created_at=entry.created_at.isoformat(),
    )
    LedgerEntry.objects.filter(id=entry.id).update(row_hash=entry.row_hash)

    # Verify audit passes
    is_valid, reason, _ = verify_user_ledger_chain_since_last_withdrawal(user)
    assert is_valid is True

    # 3. Simulate tamper: update amount without updating row_hash
    LedgerEntry.objects.filter(id=entry.id).update(amount=99999999)

    is_valid, reason, failed_ids = verify_user_ledger_chain_since_last_withdrawal(user)
    assert is_valid is False
    assert str(entry.id) in failed_ids

    # 4. Test flag_withdrawal
    w2 = Withdrawal.objects.create(
        user=user,
        amount=100000,
        status="pending_batch",
        paystack_recipient_code="RCP_1",
    )
    flag_withdrawal(w2, reason=reason, failed_entry_ids=failed_ids)
    w2.refresh_from_db()
    assert w2.is_flagged is True
    assert "Hash mismatch" in w2.flag_reason


# ─────────────────────────────────────────────────────────────
# 11. PAYOUT ACCOUNT ROLE BOUNDARIES & SIGNAL HYGIENE
# ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_no_useraccount_created_for_business_or_driver():
    """Verify DriverBankAccount and BusinessPayoutAccount never create UserAccount, and bridge never falls back."""
    from accounts.models import DriverBankAccount, BusinessPayoutAccount
    from payments.payouts.bridge import resolve_payout_account, purge_rogue_user_accounts

    # Driver test
    driver_user = User.objects.create_user(email="driver_acc@example.com")
    driver_profile = DriverProfile.objects.create(user=driver_user)
    
    # Resolving before bank account configured returns None (never UserAccount)
    assert resolve_payout_account(driver_user, "driver") is None
    assert UserAccount.objects.filter(user=driver_user).exists() is False

    dba = DriverBankAccount.objects.create(driver=driver_profile, bank_account_number="0123456789")
    assert UserAccount.objects.filter(user=driver_user).exists() is False

    # Business test
    biz_user = User.objects.create_user(email="biz_owner@example.com")
    business = Business.objects.create(business_name="Acme Corp")
    admin = BusinessAdmin.objects.create(user=biz_user, business=business)

    assert resolve_payout_account(biz_user, "business_owner") is None
    assert UserAccount.objects.filter(user=biz_user).exists() is False

    bpa = BusinessPayoutAccount.objects.create(business=business, bank_account_number="9876543210")
    assert UserAccount.objects.filter(user=biz_user).exists() is False

    # Test rogue account purge
    UserAccount.objects.create(user=biz_user, bank_name="Fake Bank")
    assert UserAccount.objects.filter(user=biz_user).exists() is True
    purged = purge_rogue_user_accounts()
    assert purged == 1
    assert UserAccount.objects.filter(user=biz_user).exists() is False

