import pytest
from unittest.mock import patch
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import (
    Business,
    BusinessAdmin,
    CustomerProfile,
    DriverProfile,
)
from accounts.services.passwords import (
    check_profile_password,
    profile_has_usable_password,
)
from accounts.services.profiles import (
    PROFILE_BUSINESS_ADMIN,
    PROFILE_CUSTOMER,
    PROFILE_DRIVER,
)
from accounts.views.account_views import (
    BusinessAdminLoginView,
    ChangePasswordView,
    DriverLoginView,
    PasswordResetView,
    RegisterCustomer,
    UserProfileView,
)
from accounts.views.business_reg_views import (
    RegisterBAdmin,
    RestaurantPhase1RegisterView,
)
from accounts.views.driver_reg_views import OnboardingPhase1View
from accounts.views.oath_views import OAuthExchangeView
from accounts.views.otp_views import VerifyEmailOTPView, VerifyPhoneOTPView
from accounts.views.security_views import verify_actor_intent
from authflow.authentication import CustomCustomerAuth
from authflow.services.jwt import issue_jwt_for_user, refresh_jwt_tokens

User = get_user_model()


def _driver_phase1_payload(email="driver@example.com", phone="+2348012345678", password="DriverPass123!"):
    return {
        "first_name": "John",
        "last_name": "Driver",
        "phone_number": phone,
        "password": password,
        "email": email,
        "gender": "male",
        "birth_date": "1995-05-10",
        "residential_address": "12 Lagos Way",
        "next_of_kin_name": "Jane Doe",
        "next_of_kin_phone": "+2348099998888",
        "next_of_kin_address": "14 Lagos Way",
    }


@pytest.mark.django_db
class TestDriverToCustomerRegistration:
    def test_driver_then_customer_phone_otp_flow(self):
        factory = APIRequestFactory()

        # 1. Create Driver via OnboardingPhase1View
        req_driver = factory.put(
            "/api/accounts/onboard/driver/phase/1/",
            _driver_phase1_payload(),
            format="json",
        )
        res_driver = OnboardingPhase1View.as_view()(req_driver)
        assert res_driver.status_code == 200
        user = User.objects.get(email="driver@example.com")
        assert hasattr(user, "driver_profile")
        assert not hasattr(user, "customer_profile")

        # 2. Same user verifies phone OTP in Customer App
        req_otp = factory.post(
            "/api/accounts/verify-otp/",
            {"phone_number": "+2348012345678", "pin_id": "pin123", "otp_code": "123456"},
            format="json",
        )
        res_otp = VerifyPhoneOTPView.as_view()(req_otp)
        assert res_otp.status_code == 200
        assert res_otp.data["is_new_user"] is True
        assert res_otp.data["needs_registration"] is True
        assert res_otp.data["prefill"]["email"] == "driver@example.com"
        assert res_otp.data["prefill"]["phone_number"] == "+2348012345678"

        # Pre-registration JWT must be unscoped (NOT "customer" and NOT "driver")
        pre_reg_token = AccessToken(res_otp.data["access"])
        assert pre_reg_token["active_profile"] is None

        # 3. Complete Customer Registration with that token
        req_reg = factory.post(
            "/api/accounts/register-user/",
            {
                "name": "John Customer",
                "email": "DRIVER@example.com",  # mixed case should match cleanly
                "phone_number": "+2348012345678",
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {res_otp.data['access']}",
        )
        res_reg = RegisterCustomer.as_view()(req_reg)
        assert res_reg.status_code == 201
        cust_access = AccessToken(res_reg.data["access"])
        assert cust_access["active_profile"] == PROFILE_CUSTOMER

        # Both profiles exist on the same User
        user.refresh_from_db()
        assert User.objects.count() == 1
        assert hasattr(user, "customer_profile")
        assert hasattr(user, "driver_profile")

        # 4. CustomCustomerAuth accepts the new customer token & refresh succeeds
        req_auth = factory.get(
            "/api/customer/",
            HTTP_AUTHORIZATION=f"Bearer {res_reg.data['access']}",
        )
        authed_user, authed_token = CustomCustomerAuth().authenticate(req_auth)
        assert authed_user.id == user.id
        assert authed_token["active_profile"] == PROFILE_CUSTOMER

        refreshed = refresh_jwt_tokens(res_reg.data["refresh"])
        assert AccessToken(refreshed["access"])["active_profile"] == PROFILE_CUSTOMER

        # 5. Subsequent OTP verify now recognizes existing CustomerProfile
        res_otp2 = VerifyPhoneOTPView.as_view()(
            factory.post(
                "/api/accounts/verify-otp/",
                {"phone_number": "+2348012345678", "pin_id": "pin123", "otp_code": "123456"},
                format="json",
            )
        )
        assert res_otp2.status_code == 200
        assert res_otp2.data["is_new_user"] is False
        assert res_otp2.data["needs_registration"] is False
        assert AccessToken(res_otp2.data["access"])["active_profile"] == PROFILE_CUSTOMER

    def test_driver_then_customer_email_otp_case_insensitive(self):
        factory = APIRequestFactory()
        user = User.objects.create(email="rider@example.com", phone_number="+2348022223333")
        DriverProfile.objects.create(user=user, first_name="Rider")

        with patch("accounts.views.otp_views.verify", return_value="RIDER@Example.com"):
            req = factory.post(
                "/api/accounts/verify-email-otp/",
                {"email": "RIDER@Example.com", "otp_code": "123456"},
                format="json",
            )
            res = VerifyEmailOTPView.as_view()(req)

        assert res.status_code == 200
        assert User.objects.count() == 1
        assert res.data["is_new_user"] is True
        assert res.data["needs_registration"] is True
        assert AccessToken(res.data["access"])["active_profile"] is None

    def test_driver_then_customer_oauth_unscoped_token(self):
        factory = APIRequestFactory()
        user = User.objects.create(email="oauthdriver@example.com", phone_number="+2348033334444")
        DriverProfile.objects.create(user=user, first_name="OAuth")

        fake_info = {
            "sub": "google-sub-123",
            "email": "OAuthDriver@example.com",
            "given_name": "OAuth",
            "family_name": "Driver",
            "picture": "https://example.com/pic.png",
        }
        with patch(
            "accounts.views.oath_views.GoogleAuthSerializer.is_valid",
            return_value=True,
        ), patch(
            "accounts.views.oath_views.GoogleAuthSerializer.validated_data",
            new_callable=lambda: property(lambda self: {"info": fake_info}),
        ):
            req = factory.post(
                "/api/accounts/oauth/exchange/",
                {"provider": "google", "id_token": "fake-token"},
                format="json",
            )
            res = OAuthExchangeView.as_view()(req)

        assert res.status_code == 200
        assert User.objects.count() == 1
        assert res.data["is_new_user"] is True
        assert res.data["needs_registration"] is True
        assert res.data["prefill"]["phone_number"] == "+2348033334444"
        assert AccessToken(res.data["access"])["active_profile"] is None


@pytest.mark.django_db
class TestOnePasswordPerProfile:
    def test_driver_and_business_admin_have_independent_passwords(self):
        factory = APIRequestFactory()
        phone = "+2348044445555"
        email = "dual@example.com"

        # 1. Onboard as Driver with DriverPass123!
        res_driver = OnboardingPhase1View.as_view()(
            factory.put(
                "/api/accounts/onboard/driver/phase/1/",
                _driver_phase1_payload(email=email, phone=phone, password="DriverPass123!"),
                format="json",
            )
        )
        assert res_driver.status_code == 200

        # 2. Register Business Admin on same phone/email, then set Business password BizPass456!
        res_badmin = RegisterBAdmin.as_view()(
            factory.put(
                "/api/accounts/onboard/admin/",
                {
                    "full_name": "Dual Owner",
                    "phone_number": phone,
                    "email": email,
                    "otp_code": "123456",
                    "pin_id": "pin123",
                },
                format="json",
            )
        )
        assert res_badmin.status_code == 200
        badmin_access = res_badmin.data["access"]

        res_bphase1 = RestaurantPhase1RegisterView.as_view()(
            factory.put(
                "/api/accounts/onboard/phase1/",
                {
                    "business_name": "Dual Kitchen",
                    "business_type": "restaurant",
                    "country": "NG",
                    "business_address": "10 Victoria Island",
                    "email": email,
                    "phone_number": phone,
                    "password": "BizPass456!",
                },
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {badmin_access}",
            )
        )
        assert res_bphase1.status_code == 201

        # 3. Driver login accepts DriverPass123! and rejects BizPass456!
        res_d_ok = DriverLoginView.as_view()(
            factory.post(
                "/api/accounts/driver-login/",
                {"phone_number": phone, "password": "DriverPass123!"},
                format="json",
            )
        )
        assert res_d_ok.status_code == 200

        res_d_bad = DriverLoginView.as_view()(
            factory.post(
                "/api/accounts/driver-login/",
                {"phone_number": phone, "password": "BizPass456!"},
                format="json",
            )
        )
        assert res_d_bad.status_code == 401

        # 4. Business Admin login accepts BizPass456! and rejects DriverPass123!
        res_b_ok = BusinessAdminLoginView.as_view()(
            factory.post(
                "/api/accounts/business/admin-login/",
                {"phone_number": phone, "password": "BizPass456!"},
                format="json",
            )
        )
        assert res_b_ok.status_code == 200

        res_b_bad = BusinessAdminLoginView.as_view()(
            factory.post(
                "/api/accounts/business/admin-login/",
                {"phone_number": phone, "password": "DriverPass123!"},
                format="json",
            )
        )
        assert res_b_bad.status_code == 401

        # 5. ChangePasswordView with Driver token cannot target BusinessAdmin via body profile_type
        res_chg_cross = ChangePasswordView.as_view()(
            factory.post(
                "/api/accounts/change-password/",
                {
                    "password": "BizPass456!",
                    "new_password": "Hijacked999!",
                    "profile_type": PROFILE_BUSINESS_ADMIN,
                },
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {res_d_ok.data['access']}",
            )
        )
        assert res_chg_cross.status_code == 400

        # ChangePasswordView with Driver token changes ONLY Driver password
        res_chg = ChangePasswordView.as_view()(
            factory.post(
                "/api/accounts/change-password/",
                {"password": "DriverPass123!", "new_password": "DriverNew789!"},
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {res_d_ok.data['access']}",
            )
        )
        assert res_chg.status_code == 200

        user = User.objects.get(email=email)
        assert check_profile_password(user, PROFILE_DRIVER, "DriverNew789!") is True
        assert check_profile_password(user, PROFILE_DRIVER, "DriverPass123!") is False
        assert check_profile_password(user, PROFILE_BUSINESS_ADMIN, "BizPass456!") is True

        # 6. PasswordResetView without profile_type rejects ambiguity when multiple passworded profiles exist
        with patch("accounts.views.account_views.verify", return_value=email):
            res_ambig = PasswordResetView.as_view()(
                factory.post(
                    "/api/accounts/password-reset/",
                    {"email": email, "otp_code": "123456", "new_password": "ResetPass999!"},
                    format="json",
                )
            )
            assert res_ambig.status_code == 400
            assert set(res_ambig.data["available_profiles"]) == {PROFILE_DRIVER, PROFILE_BUSINESS_ADMIN}

            # With profile_type="businessadmin", resets ONLY BusinessAdmin password
            res_reset = PasswordResetView.as_view()(
                factory.post(
                    "/api/accounts/password-reset/",
                    {
                        "email": email,
                        "otp_code": "123456",
                        "new_password": "BizReset999!",
                        "profile_type": PROFILE_BUSINESS_ADMIN,
                    },
                    format="json",
                )
            )
            assert res_reset.status_code == 200

        user = User.objects.get(email=email)
        assert check_profile_password(user, PROFILE_BUSINESS_ADMIN, "BizReset999!") is True
        assert check_profile_password(user, PROFILE_DRIVER, "DriverNew789!") is True

    def test_customer_security_intent_not_polluted_by_driver_password(self, monkeypatch):
        from common.otp.base import OTPManager

        monkeypatch.setattr(OTPManager, "send", lambda channel, identifier: True)

        factory = APIRequestFactory()
        user = User.objects.create(email="custdrv@example.com", phone_number="+2348055556666")
        user.set_unusable_password()
        user.save()
        CustomerProfile.objects.create(user=user, name="Cust")
        drv = DriverProfile.objects.create(user=user, first_name="Drv")
        drv.set_password("DriverSecret123!")
        drv.save(update_fields=["password_hash"])

        assert profile_has_usable_password(user, PROFILE_DRIVER) is True
        assert profile_has_usable_password(user, PROFILE_CUSTOMER) is False

        cust_tokens = issue_jwt_for_user(user, active_profile=PROFILE_CUSTOMER)
        req = factory.post("/api/accounts/security/test/", {}, format="json")
        force_authenticate(req, user=user, token=AccessToken(cust_tokens["access"]))

        verified, resp = verify_actor_intent(user, req)
        assert verified is False
        # Should ask for OTP (202), NOT fail with 401 demanding Driver's password
        assert resp.status_code == 202
        assert resp.data["status"] == "auth_otp_required"

    def test_driver_phase1_validation_failure_leaves_no_orphan_user(self):
        factory = APIRequestFactory()
        User.objects.create(email="existing@example.com", phone_number="+2348066667777")

        # Different email + existing phone number should fail cleanly without creating a 2nd User
        res = OnboardingPhase1View.as_view()(
            factory.put(
                "/api/accounts/onboard/driver/phase/1/",
                _driver_phase1_payload(email="neworphan@example.com", phone="+2348066667777"),
                format="json",
            )
        )
        assert res.status_code == 400
        assert User.objects.count() == 1
        assert not User.objects.filter(email="neworphan@example.com").exists()

    def test_user_profile_view_respects_active_profile_claim(self):
        factory = APIRequestFactory()
        user = User.objects.create(email="both@example.com", phone_number="+2348077778888")
        CustomerProfile.objects.create(user=user, name="Customer Side")
        DriverProfile.objects.create(user=user, first_name="Driver", last_name="Side")

        driver_tokens = issue_jwt_for_user(user, active_profile=PROFILE_DRIVER)
        req = factory.get(
            "/api/accounts/profile/",
            HTTP_AUTHORIZATION=f"Bearer {driver_tokens['access']}",
        )
        res = UserProfileView.as_view()(req)
        assert res.status_code == 200
        assert res.data["active_profile_type"] == PROFILE_DRIVER
        assert res.data["profile"]["first_name"] == "Driver"
