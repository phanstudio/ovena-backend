import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import CustomerProfile, DriverProfile, ProfileBase
from accounts.services.profiles import (
    PROFILE_CUSTOMER,
    PROFILE_DRIVER,
    get_profile,
    has_profile,
    resolve_active_profile_type,
)
from authflow.services import issue_jwt_for_user


pytestmark = pytest.mark.django_db


def _create_profile_base(user, profile_type: str):
    return ProfileBase.objects.create(user=user, profile_type=profile_type)


def test_get_profile_and_has_profile_customer():
    user_model = get_user_model()
    user = user_model.objects.create(
        email="profile-resolver-customer@example.com",
        phone_number="+2348000001201",
    )
    base = _create_profile_base(user, PROFILE_CUSTOMER)
    customer = CustomerProfile.objects.create(base_profile=base, user=user)

    assert has_profile(user, PROFILE_CUSTOMER) is True
    assert get_profile(user, PROFILE_CUSTOMER).pk == customer.pk
    assert has_profile(user, PROFILE_DRIVER) is False


def test_resolve_active_profile_type_prefers_header():
    user_model = get_user_model()
    user = user_model.objects.create(
        email="profile-resolver-both@example.com",
        phone_number="+2348000001202",
    )
    cbase = _create_profile_base(user, PROFILE_CUSTOMER)
    dbase = _create_profile_base(user, PROFILE_DRIVER)
    CustomerProfile.objects.create(base_profile=cbase, user=user)
    DriverProfile.objects.create(base_profile=dbase, user=user)

    req = APIRequestFactory().get("/", HTTP_X_PROFILE_TYPE=PROFILE_DRIVER)
    req.auth = {}
    resolved = resolve_active_profile_type(
        request=req,
        user=user,
        allowed_types=[PROFILE_CUSTOMER, PROFILE_DRIVER],
    )
    assert resolved == PROFILE_DRIVER


def test_issue_jwt_with_active_profile_claim():
    user_model = get_user_model()
    user = user_model.objects.create(
        email="profile-token@example.com",
        phone_number="+2348000001203",
    )
    dbase = _create_profile_base(user, PROFILE_DRIVER)
    DriverProfile.objects.create(base_profile=dbase, user=user)

    tokens = issue_jwt_for_user(user, active_profile=PROFILE_DRIVER)
    access = AccessToken(tokens["access"])

    assert access["active_profile"] == PROFILE_DRIVER
    assert PROFILE_DRIVER in access["roles"]

