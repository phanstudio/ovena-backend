import pytest
from unittest.mock import MagicMock, patch
from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.auth import get_user_model
from common.otp.service import MultiChannelOTPService
from common.otp.base import OTPManager
from common.otp.exceptions import OTPDeliveryError
from accounts.views.security_views import verify_actor_intent, SetPasswordView
from payments.models import UserAccount
from accounts.models import Business, BusinessAdmin, BusinessOnboardStatus, DriverProfile, DriverOnboardingSubmission
from accounts.views.driver_reg_views import OnboardingPhase1View
from accounts.views.business_reg_views import RegisterBAdmin

User = get_user_model()


@pytest.mark.django_db
def test_multichannel_otp_send_with_sms_fallback_to_email():
    """When SMS channel fails, MultiChannelOTPService falls back to email channel."""
    def fake_send(channel, identifier):
        if channel == "phone":
            raise OTPDeliveryError("SMS Provider Gateway Timeout")
        return True

    with patch.object(OTPManager, "send", side_effect=fake_send) as mock_send:
        result = MultiChannelOTPService.send_with_fallback(
            phone_number="+2348011112222",
            email="fallback_user@test.com",
            prefer_email=False,
        )

        assert result["channel_used"] == "email"
        assert result["fallback"] is True
        assert mock_send.call_count == 2


@pytest.mark.django_db
def test_verify_actor_intent_with_password():
    """Actor intent verification succeeds with valid password."""
    factory = APIRequestFactory()
    user = User.objects.create_user(email="pwd_user@test.com")
    user.set_password("SecretPassword123!")
    user.save()

    req = factory.post("/api/security/test/", {"password": "SecretPassword123!"}, format="json")
    force_authenticate(req, user=user)

    verified, resp = verify_actor_intent(user, req)
    assert verified is True
    assert resp is None


@pytest.mark.django_db
def test_verify_actor_intent_with_transaction_pin():
    """Actor intent verification succeeds with valid transaction PIN."""
    factory = APIRequestFactory()
    user = User.objects.create_user(email="pin_user@test.com")
    user.set_unusable_password()
    user.save()
    account = UserAccount.objects.create(user=user)
    account.set_transaction_pin("1234")

    req = factory.post("/api/security/test/", {"transaction_pin": "1234"}, format="json")
    force_authenticate(req, user=user)

    verified, resp = verify_actor_intent(user, req)
    assert verified is True
    assert resp is None


@pytest.mark.django_db
def test_verify_actor_intent_oauth_user_otp_fallback(monkeypatch):
    """OAuth user with no password and no PIN requires intent verification via OTP."""
    monkeypatch.setattr(OTPManager, "send", lambda channel, identifier: True)

    factory = APIRequestFactory()
    user = User.objects.create_user(email="oauth_user@test.com")
    user.set_unusable_password()
    user.save()

    # Without OTP verification code
    req = factory.post("/api/security/test/", {}, format="json")
    force_authenticate(req, user=user)

    verified, resp = verify_actor_intent(user, req)
    assert verified is False
    assert resp.status_code == 202
    assert resp.data["status"] == "auth_otp_required"


@pytest.mark.django_db
def test_set_password_view_for_oauth_user(monkeypatch):
    """OAuth user can set initial password using SetPasswordView when verified."""
    monkeypatch.setattr(OTPManager, "verify", lambda otp_code: "oauth_setpwd@test.com")

    factory = APIRequestFactory()
    user = User.objects.create_user(email="oauth_setpwd@test.com")
    user.set_unusable_password()
    user.save()

    req = factory.post(
        "/api/security/set-password/",
        {
            "new_password": "NewSecurePassword123!",
            "auth_otp_code": "123456",
        },
        format="json",
    )
    force_authenticate(req, user=user)

    view = SetPasswordView.as_view()
    res = view(req)

    assert res.status_code == 200
    user.refresh_from_db()
    assert user.has_usable_password() is True
    assert user.check_password("NewSecurePassword123!") is True


@pytest.mark.django_db
def test_set_password_view_rejected_for_regular_password_user():
    """Users who already have a usable password cannot use set-password view."""
    factory = APIRequestFactory()
    user = User.objects.create_user(email="regular_pwd@test.com")
    user.set_password("ExistingPassword123!")
    user.save()

    req = factory.post(
        "/api/security/set-password/",
        {"new_password": "NewSecurePassword123!"},
        format="json",
    )
    force_authenticate(req, user=user)

    view = SetPasswordView.as_view()
    res = view(req)

    assert res.status_code == 400
    assert "already configured" in res.data["error"]


@pytest.mark.django_db
def test_driver_onboarding_reentrance_guard():
    """Approved driver submission blocks re-entry into onboarding phases."""
    factory = APIRequestFactory()
    user = User.objects.create_user(email="driver_approved@test.com")
    profile = DriverProfile.objects.create(user=user)
    submission = DriverOnboardingSubmission.objects.create(
        driver=profile,
        status=DriverOnboardingSubmission.STATUS_APPROVED,
    )

    req = factory.put(
        "/api/drivers/onboarding/phase1/",
        {
            "first_name": "John",
            "last_name": "Doe",
            "gender": "male",
            "birth_date": "1990-01-01",
            "residential_address": "123 Street",
            "phone_number": "+2348011112222",
            "email": "driver_approved@test.com",
            "password": "Password123!",
        },
        format="json",
    )
    force_authenticate(req, user=user)

    view = OnboardingPhase1View.as_view()
    res = view(req)

    assert res.status_code == 403
    assert "already been approved" in res.data["detail"].lower()


@pytest.mark.django_db
def test_business_admin_reentrance_guard():
    """Completed business onboarding blocks unauthenticated RegisterBAdmin call."""
    factory = APIRequestFactory()
    user = User.objects.create_user(email="biz_complete@test.com", phone_number="+2348099998888")
    biz = Business.objects.create(business_name="Complete Biz Ltd")
    admin = BusinessAdmin.objects.create(user=user, business=biz)
    BusinessOnboardStatus.objects.create(admin=admin, is_onboarding_complete=True)

    # RegisterBAdmin is PUT /business/admin/register/
    req = factory.put(
        "/api/business/admin/register/",
        {
            "full_name": "Hacker Attempt",
            "email": "hacked@test.com",
            "phone_number": "+2348099998888",
            "otp_code": "123456",
            "pin_id": "pin-123",
        },
        format="json",
    )

    view = RegisterBAdmin.as_view()
    res = view(req)

    assert res.status_code == 403
    assert "already completed" in res.data["error"].lower()
