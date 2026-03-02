import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import CustomerProfile, DriverProfile, ProfileBase
from accounts.services.roles import get_user_roles, has_role
from authflow.services import issue_jwt_for_user


pytestmark = pytest.mark.django_db


def test_roles_are_profile_derived_with_legacy_fallback():
    user_model = get_user_model()
    user = user_model.objects.create(
        email="roles@example.com",
        phone_number="+2348000001000",
        role="buisnessstaff",
    )
    pb = ProfileBase.objects.create(
        user=user,
        profile_type=ProfileBase.PROFILE_CUSTOMER,
    ) # remove after legacy
    CustomerProfile.objects.create(user=user, base_profile=pb)
    roles = get_user_roles(user)

    assert "customer" in roles
    assert "businessstaff" in roles
    assert has_role(user, "customer") is True
    assert has_role(user, "buisnessstaff") is True


# def test_user_with_customer_and_driver_has_both_roles():
#     user_model = get_user_model()
#     user = user_model.objects.create(
#         email="multi@example.com",
#         phone_number="+2348000001001",
#         role="customer",
#     )
#     CustomerProfile.objects.create(user=user)
#     DriverProfile.objects.create(user=user)

#     roles = get_user_roles(user)
#     assert roles.issuperset({"customer", "driver"})
#     assert user.has_role("driver") is True


# def test_jwt_contains_roles_claim():
#     user_model = get_user_model()
#     user = user_model.objects.create(
#         email="jwtroles@example.com",
#         phone_number="+2348000001002",
#         role="driver",
#     )
#     DriverProfile.objects.create(user=user)

#     token_pair = issue_jwt_for_user(user)
#     access = AccessToken(token_pair["access"])

#     assert "roles" in access
#     assert "driver" in access["roles"]

