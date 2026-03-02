import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from accounts.models import CustomerProfile, DriverProfile
from referrals.services import (
    apply_referral_code,
    convert_referral_once,
    ensure_profile_base,
    referral_count,
    successful_referrals,
)


pytestmark = pytest.mark.django_db


@pytest.fixture
def user_model():
    return get_user_model()


@pytest.fixture
def customer_profile(user_model):
    user = user_model.objects.create(
        email="customer1@example.com",
        phone_number="+2348010001001",
        role="customer",
    )
    return CustomerProfile.objects.create(user=user)


@pytest.fixture
def customer_profile_2(user_model):
    user = user_model.objects.create(
        email="customer2@example.com",
        phone_number="+2348010001002",
        role="customer",
    )
    return CustomerProfile.objects.create(user=user)


@pytest.fixture
def driver_profile(user_model):
    user = user_model.objects.create(
        email="driver1@example.com",
        phone_number="+2348010002001",
        role="driver",
    )
    return DriverProfile.objects.create(user=user)


def test_customer_refers_customer_success(customer_profile, customer_profile_2):
    referrer_base = ensure_profile_base(customer_profile)
    referral = apply_referral_code(profile=customer_profile_2, code=referrer_base.referral_code)

    assert referral.referrer_user_id == customer_profile.user_id
    assert referral.referee_user_id == customer_profile_2.user_id


def test_customer_refers_driver_success(customer_profile, driver_profile):
    referrer_base = ensure_profile_base(customer_profile)
    referral = apply_referral_code(profile=driver_profile, code=referrer_base.referral_code)

    assert referral.referrer_user_id == customer_profile.user_id
    assert referral.referee_user_id == driver_profile.user_id


def test_prevent_self_referral_same_user_cross_profiles(user_model):
    user = user_model.objects.create(
        email="dual@example.com",
        phone_number="+2348010099999",
        role="driver",
    )
    customer = CustomerProfile.objects.create(user=user)
    driver = DriverProfile.objects.create(user=user)

    customer_base = ensure_profile_base(customer)

    with pytest.raises(ValidationError):
        apply_referral_code(profile=driver, code=customer_base.referral_code)


def test_prevent_multiple_referrals_per_referee_user(user_model, customer_profile):
    target_user = user_model.objects.create(
        email="target@example.com",
        phone_number="+2348010088888",
        role="customer",
    )
    target_customer = CustomerProfile.objects.create(user=target_user)
    target_driver = DriverProfile.objects.create(user=target_user)

    referrer_code = ensure_profile_base(customer_profile).referral_code
    apply_referral_code(profile=target_customer, code=referrer_code)

    with pytest.raises(ValidationError):
        apply_referral_code(profile=target_driver, code=referrer_code)


def test_referral_count_and_successful_referrals(customer_profile, customer_profile_2):
    referrer_code = ensure_profile_base(customer_profile).referral_code
    apply_referral_code(profile=customer_profile_2, code=referrer_code)

    assert referral_count(customer_profile) == 1
    assert successful_referrals(customer_profile) == 0

    changed = convert_referral_once(referee_profile=customer_profile_2)
    assert changed is True
    assert successful_referrals(customer_profile) == 1

    changed_again = convert_referral_once(referee_profile=customer_profile_2)
    assert changed_again is False

