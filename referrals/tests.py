from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from accounts.models import CustomerProfile, DriverProfile
from referrals.models import ProfileReferral
from referrals.constants import (
    ROLE_CUSTOMER,
    ROLE_DRIVER,
    ROLE_BUSINESS_ADMIN,
    FRAUD_STATUS_CLEAN,
    FRAUD_STATUS_FLAGGED,
    MIN_QUALIFYING_ORDER_AMOUNT_KOBO,
)
from referrals.services import (
    apply_referral_code,
    convert_referral_for_customer,
    convert_referral_for_driver,
    referral_stats,
)

User = get_user_model()


class ReferralSystemTests(TestCase):
    def setUp(self):
        # Create Referrer User & Customer Profile
        self.referrer_user = User.objects.create_user(
            email="referrer@test.com",
            phone_number="+2348011111111",
        )
        self.referrer_customer = CustomerProfile.objects.create(
            user=self.referrer_user,
            name="Referrer One",
        )

        # Create Referee User 1
        self.referee_user1 = User.objects.create_user(
            email="referee1@test.com",
            phone_number="+2348022222222",
        )
        self.referee_customer1 = CustomerProfile.objects.create(
            user=self.referee_user1,
            name="Referee One",
        )

        # Create Referee User 2 (Driver)
        self.driver_user = User.objects.create_user(
            email="driver@test.com",
            phone_number="+2348033333333",
        )
        self.driver_profile = DriverProfile.objects.create(
            user=self.driver_user,
            first_name="Driver",
            last_name="Test",
        )

    def test_apply_referral_code_customer_success(self):
        """A valid customer can apply a customer referral code."""
        code = self.referrer_customer.referral_code
        referral = apply_referral_code(
            user=self.referee_user1,
            profile=self.referee_customer1,
            code=code,
            role=ROLE_CUSTOMER,
            device_id="device-abc-123",
            ip_address="192.168.1.10",
        )
        self.assertEqual(referral.referrer_user, self.referrer_user)
        self.assertEqual(referral.referee_user, self.referee_user1)
        self.assertEqual(referral.referrer_role, ROLE_CUSTOMER)
        self.assertEqual(referral.referee_role, ROLE_CUSTOMER)
        self.assertEqual(referral.fraud_status, FRAUD_STATUS_CLEAN)

    def test_apply_referral_code_driver_success(self):
        """A driver applicant can apply a referral code."""
        code = self.referrer_customer.referral_code
        referral = apply_referral_code(
            user=self.driver_user,
            profile=self.driver_profile,
            code=code,
            role=ROLE_DRIVER,
            device_id="device-xyz-789",
            ip_address="192.168.1.11",
        )
        self.assertEqual(referral.referrer_user, self.referrer_user)
        self.assertEqual(referral.referee_user, self.driver_user)
        self.assertEqual(referral.referee_role, ROLE_DRIVER)
        self.assertEqual(referral.fraud_status, FRAUD_STATUS_CLEAN)

    def test_self_referral_rejected(self):
        """User cannot use their own referral code."""
        code = self.referrer_customer.referral_code
        with self.assertRaises(ValidationError) as ctx:
            apply_referral_code(
                user=self.referrer_user,
                profile=self.referrer_customer,
                code=code,
                role=ROLE_CUSTOMER,
            )
        self.assertIn("own referral code", str(ctx.exception))

    def test_circular_referral_rejected(self):
        """Circular referrals (A refers B, then B refers A) must be blocked."""
        # 1. A refers B
        code_a = self.referrer_customer.referral_code
        apply_referral_code(
            user=self.referee_user1,
            profile=self.referee_customer1,
            code=code_a,
            role=ROLE_CUSTOMER,
        )

        # 2. B attempts to refer A
        code_b = self.referee_customer1.referral_code
        with self.assertRaises(ValidationError) as ctx:
            apply_referral_code(
                user=self.referrer_user,
                profile=self.referrer_customer,
                code=code_b,
                role=ROLE_CUSTOMER,
            )
        self.assertIn("Circular referral", str(ctx.exception))

    def test_unsupported_role_rejected(self):
        """Unsupported roles (e.g. businessadmin) cannot participate in referrals."""
        code = self.referrer_customer.referral_code
        with self.assertRaises(ValidationError) as ctx:
            apply_referral_code(
                user=self.referee_user1,
                profile=self.referee_customer1,
                code=code,
                role=ROLE_BUSINESS_ADMIN,
            )
        self.assertIn("currently only open to customers and drivers", str(ctx.exception))

    def test_device_fingerprint_flagged(self):
        """If referee uses the exact same device ID as the referrer, referral is soft-flagged."""
        code = self.referrer_customer.referral_code
        # Mark that referrer previously used device "shared-phone-1"
        ProfileReferral.objects.create(
            referrer_user=self.referee_user1,
            referee_user=self.referrer_user,
            referee_device_id="shared-phone-1",
        )

        # Now new user tries to use referrer's code on the same device
        new_user = User.objects.create_user(email="newuser@test.com", phone_number="+2348044444444")
        new_customer = CustomerProfile.objects.create(user=new_user, name="New")

        referral = apply_referral_code(
            user=new_user,
            profile=new_customer,
            code=code,
            role=ROLE_CUSTOMER,
            device_id="shared-phone-1",
        )
        self.assertEqual(referral.fraud_status, FRAUD_STATUS_FLAGGED)
        self.assertIn("matches referrer device history", referral.fraud_reason)

    def test_ip_velocity_rate_limit(self):
        """No more than 3 referrals from the same IP address in 24 hours."""
        code = self.referrer_customer.referral_code
        ip = "192.168.1.99"

        # Apply 3 referrals successfully
        for i in range(3):
            u = User.objects.create_user(email=f"ipuser{i}@test.com", phone_number=f"+234805555555{i}")
            p = CustomerProfile.objects.create(user=u, name=f"IP User {i}")
            apply_referral_code(user=u, profile=p, code=code, role=ROLE_CUSTOMER, ip_address=ip)

        # 4th application from the same IP must be rate-limited
        fourth_user = User.objects.create_user(email="ipuser4@test.com", phone_number="+2348066666666")
        fourth_profile = CustomerProfile.objects.create(user=fourth_user, name="Fourth")
        with self.assertRaises(ValidationError) as ctx:
            apply_referral_code(user=fourth_user, profile=fourth_profile, code=code, role=ROLE_CUSTOMER, ip_address=ip)
        self.assertIn("Too many referral signups from this network", str(ctx.exception))

    def test_order_conversion_customer_qualifies(self):
        """Customer referral converts on a qualifying delivered order."""
        code = self.referrer_customer.referral_code
        referral = apply_referral_code(
            user=self.referee_user1,
            profile=self.referee_customer1,
            code=code,
            role=ROLE_CUSTOMER,
        )
        self.assertIsNone(referral.converted_at)

        # Mock qualifying order
        class MockOrder:
            total_price = 2500  # ₦2,500 > ₦1,500 threshold
            sale = None

        converted = convert_referral_for_customer(user=self.referee_user1, order=MockOrder())
        self.assertTrue(converted)

        referral.refresh_from_db()
        self.assertIsNotNone(referral.converted_at)

    def test_order_conversion_below_minimum_basket_rejected(self):
        """Customer referral does not convert if order is below minimum basket size."""
        code = self.referrer_customer.referral_code
        referral = apply_referral_code(
            user=self.referee_user1,
            profile=self.referee_customer1,
            code=code,
            role=ROLE_CUSTOMER,
        )

        class LowValueOrder:
            total_price = 500  # ₦500 < ₦1,500 threshold
            sale = None

        converted = convert_referral_for_customer(user=self.referee_user1, order=LowValueOrder())
        self.assertFalse(converted)

        referral.refresh_from_db()
        self.assertIsNone(referral.converted_at)
