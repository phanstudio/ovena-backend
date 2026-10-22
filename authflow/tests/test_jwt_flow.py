import pytest
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIRequestFactory
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from accounts.models import (
    CustomerProfile,
    DriverProfile,
    Business,
    BusinessAdmin,
    Branch,
    PrimaryAgent,
    Suspension,
    Appeal,
)
from payments.models.subscription import Plan, Feature, Subscription, PlanAudience
from authflow.services.jwt import (
    issue_jwt_for_user,
    issue_jwt_for_user_with_plan,
    refresh_jwt_tokens,
    build_jwt_claims,
    compute_is_approved,
)
from authflow.subscritpion import PlanFeatureService
from authflow.permissions import (
    HasFeature,
    NeedsApprovalPermission,
    NeedsVerficationsPermission,
    IsNotSuspended,
)
from authflow.authentication import CustomJWtAuth, CustomDriverAuth, CustomCustomerAuth
from accounts.services.profiles import (
    PROFILE_CUSTOMER,
    PROFILE_DRIVER,
    PROFILE_BUSINESS_ADMIN,
    PROFILE_BUSINESS_STAFF,
)
from accounts.services.suspensions import is_suspended, clear_suspension_cache
from accounts.services.roles import has_role

User = get_user_model()


@pytest.fixture
def test_user(db):
    user = User.objects.create(
        email="testuser@example.com",
        phone_number="+2348011112222",
        is_active=True,
        is_approved=True,
    )
    CustomerProfile.objects.create(user=user)
    return user


@pytest.fixture
def driver_user(db):
    user = User.objects.create(
        email="driver@example.com",
        phone_number="+2348022223333",
        is_active=True,
        is_approved=False,
    )
    CustomerProfile.objects.create(user=user)
    DriverProfile.objects.create(user=user, first_name="John", last_name="Doe")
    return user


@pytest.fixture
def business_user(db):
    user = User.objects.create(
        email="merchant@example.com",
        phone_number="+2348033334444",
        is_active=True,
        is_approved=True,
    )
    business = Business.objects.create(business_name="Tasty Bites", onboarding_complete=False)
    BusinessAdmin.objects.create(user=user, business=business)
    return user


@pytest.fixture
def test_plan_with_features(db):
    plan = Plan.objects.create(
        name="Premium Plan",
        audience=PlanAudience.BUSINESS,
        paystack_plan_code="PLN_test123",
        amount=500000,
    )
    feat1 = Feature.objects.create(code="priority-search")
    feat2 = Feature.objects.create(code="banner")
    plan.features.add(feat1, feat2)
    return plan


@pytest.mark.django_db
class TestTokenIssuanceAndClaims:
    def test_claims_structure_customer(self, test_user):
        tokens = issue_jwt_for_user(test_user, active_profile=PROFILE_CUSTOMER)
        refresh = RefreshToken(tokens["refresh"])
        access = refresh.access_token

        assert access["active_profile"] == PROFILE_CUSTOMER
        assert access["is_approved"] is True
        assert access["is_active"] is True
        assert access["suspended"] is False
        assert access["plan_id"] is None

    def test_claims_structure_driver_approval(self, driver_user):
        # Driver is_approved is False initially
        tokens = issue_jwt_for_user(driver_user, active_profile=PROFILE_DRIVER)
        access = RefreshToken(tokens["refresh"]).access_token

        assert access["active_profile"] == PROFILE_DRIVER
        assert access["is_approved"] is False

        # Now approve driver
        driver_user.is_approved = True
        driver_user.save()

        tokens2 = issue_jwt_for_user(driver_user, active_profile=PROFILE_DRIVER)
        access2 = RefreshToken(tokens2["refresh"]).access_token
        assert access2["is_approved"] is True

    def test_claims_structure_business_onboarding(self, business_user):
        # Business onboarding_complete is False
        tokens = issue_jwt_for_user(business_user, active_profile=PROFILE_BUSINESS_ADMIN)
        access = RefreshToken(tokens["refresh"]).access_token
        assert access["is_approved"] is False

        # Complete onboarding
        business = business_user.business_admin.business
        business.onboarding_complete = True
        business.save()

        tokens2 = issue_jwt_for_user(business_user, active_profile=PROFILE_BUSINESS_ADMIN)
        access2 = RefreshToken(tokens2["refresh"]).access_token
        assert access2["is_approved"] is True

    def test_issue_jwt_for_inactive_user_raises(self, test_user):
        test_user.is_active = False
        test_user.save()

        with pytest.raises(AuthenticationFailed):
            issue_jwt_for_user(test_user, active_profile=PROFILE_CUSTOMER)


@pytest.mark.django_db
class TestPlanFeatureService:
    def test_feature_caching_and_db_fallback(self, test_plan_with_features):
        plan_id = test_plan_with_features.id
        PlanFeatureService.invalidate_plan_features_cache(plan_id)

        features = PlanFeatureService.get_plan_features(plan_id)
        assert "priority-search" in features
        assert "banner" in features
        assert "non-existent" not in features

        # Test strict checking (no wildcard)
        assert PlanFeatureService.has_feature(plan_id, "priority-search") is True
        assert PlanFeatureService.has_feature(plan_id, "banner") is True
        assert PlanFeatureService.has_feature(plan_id, "non-existent") is False
        assert PlanFeatureService.has_feature(plan_id, "*") is False

    def test_has_feature_permission(self, test_user, test_plan_with_features):
        perm = HasFeature()
        factory = APIRequestFactory()

        # View requiring "banner"
        class MockView:
            required_feature = ["banner"]

        request = factory.get("/")
        # Token with plan_id
        request.auth = {"plan_id": test_plan_with_features.id}
        request.user = test_user
        assert perm.has_permission(request, MockView()) is True

        # View requiring a feature not on the plan
        class MockViewExclusive:
            required_feature = ["carousel"]

        assert perm.has_permission(request, MockViewExclusive()) is False

        # Request without plan_id
        request.auth = {"plan_id": None}
        assert perm.has_permission(request, MockView()) is False


@pytest.mark.django_db
class TestRoleScopedSuspensions:
    def test_suspension_is_role_scoped(self, driver_user):
        clear_suspension_cache(driver_user.id)

        # Suspend user as driver
        Suspension.objects.create(user=driver_user, role=PROFILE_DRIVER, level="temporary")
        clear_suspension_cache(driver_user.id)

        # Driver profile is suspended
        assert is_suspended(driver_user.id, role=PROFILE_DRIVER) is True
        # Customer profile is NOT suspended
        assert is_suspended(driver_user.id, role=PROFILE_CUSTOMER) is False

        # Tokens reflect role-scoped suspension
        driver_tokens = issue_jwt_for_user(driver_user, active_profile=PROFILE_DRIVER)
        driver_access = RefreshToken(driver_tokens["refresh"]).access_token
        assert driver_access["suspended"] is True

        cust_tokens = issue_jwt_for_user(driver_user, active_profile=PROFILE_CUSTOMER)
        cust_access = RefreshToken(cust_tokens["refresh"]).access_token
        assert cust_access["suspended"] is False

    def test_is_not_suspended_permission(self, driver_user):
        perm = IsNotSuspended()
        factory = APIRequestFactory()

        request = factory.get("/")
        request.user = driver_user
        request.auth = {"active_profile": PROFILE_DRIVER, "suspended": True}

        assert perm.has_permission(request, None) is False

        # Customer token is not suspended
        request.auth = {"active_profile": PROFILE_CUSTOMER, "suspended": False}
        assert perm.has_permission(request, None) is True

    def test_appeal_approval_clears_suspension(self, driver_user):
        suspension = Suspension.objects.create(user=driver_user, role=PROFILE_DRIVER, level="temporary")
        clear_suspension_cache(driver_user.id)
        appeal = Appeal.objects.create(suspension=suspension)

        # Cache confirms suspended
        assert is_suspended(driver_user.id, role=PROFILE_DRIVER) is True


        # Approve appeal
        reviewer = User.objects.create(email="admin_rev@example.com")
        appeal.approve(reviewer)

        # Cache should be cleared and DB reflects lifted
        assert is_suspended(driver_user.id, role=PROFILE_DRIVER) is False


@pytest.mark.django_db
class TestLockedIdentityAndRefresh:
    def test_token_refresh_updates_claims(self, test_user, test_plan_with_features):
        # 1. Issue token without subscription
        tokens = issue_jwt_for_user_with_plan(test_user, active_profile=PROFILE_CUSTOMER)
        old_access = RefreshToken(tokens["refresh"]).access_token
        assert old_access["plan_id"] is None
        assert old_access["active_profile"] == PROFILE_CUSTOMER

        # 2. Add subscription to user
        Subscription.objects.create(user=test_user, plan=test_plan_with_features, active=True)

        # 3. Refresh token
        new_tokens = refresh_jwt_tokens(tokens["refresh"])
        new_access = RefreshToken(new_tokens["refresh"]).access_token

        # Verify new access token received updated plan_id and preserved locked active_profile
        assert new_access["plan_id"] == test_plan_with_features.id
        assert new_access["active_profile"] == PROFILE_CUSTOMER

    def test_token_refresh_preserves_driver_identity(self, driver_user):
        tokens = issue_jwt_for_user(driver_user, active_profile=PROFILE_DRIVER)

        # Approve driver in DB
        driver_user.is_approved = True
        driver_user.save()

        new_tokens = refresh_jwt_tokens(tokens["refresh"])
        new_access = RefreshToken(new_tokens["refresh"]).access_token

        assert new_access["active_profile"] == PROFILE_DRIVER
        assert new_access["is_approved"] is True

    def test_token_refresh_blocks_inactive_user(self, test_user):
        tokens = issue_jwt_for_user(test_user, active_profile=PROFILE_CUSTOMER)

        test_user.is_active = False
        test_user.save()

        with pytest.raises(AuthenticationFailed):
            refresh_jwt_tokens(tokens["refresh"])

    def test_authentication_enforces_active_profile(self, driver_user):
        factory = APIRequestFactory()
        auth = CustomDriverAuth()

        # Valid driver token
        tokens = issue_jwt_for_user(driver_user, active_profile=PROFILE_DRIVER)
        request = factory.get("/", HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        user, token = auth.authenticate(request)
        assert user == driver_user
        assert token["active_profile"] == PROFILE_DRIVER
        assert request.active_profile == PROFILE_DRIVER

        # Using customer token on driver endpoint fails
        cust_tokens = issue_jwt_for_user(driver_user, active_profile=PROFILE_CUSTOMER)
        request2 = factory.get("/", HTTP_AUTHORIZATION=f"Bearer {cust_tokens['access']}")

        with pytest.raises(AuthenticationFailed):
            auth.authenticate(request2)

    def test_has_role_helper_with_token(self, driver_user):
        factory = APIRequestFactory()
        request = factory.get("/")
        request.auth = {"active_profile": PROFILE_DRIVER}
        request.user = driver_user

        assert has_role(request, PROFILE_DRIVER) is True
        assert has_role(request, PROFILE_CUSTOMER) is False

    def test_refresh_token_view_api(self, test_user):
        from accounts.views.jwt_views import RefreshTokenView
        factory = APIRequestFactory()
        view = RefreshTokenView.as_view()

        tokens = issue_jwt_for_user(test_user, active_profile=PROFILE_CUSTOMER)
        request = factory.post("/api/accounts/refresh/", {"refresh": tokens["refresh"]}, format="json")
        response = view(request)
        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh" in response.data

    def test_rotate_token_view_api(self, test_user):
        from accounts.views.jwt_views import RotateTokenView
        factory = APIRequestFactory()
        view = RotateTokenView.as_view()

        tokens = issue_jwt_for_user(test_user, active_profile=PROFILE_CUSTOMER)
        request = factory.post("/api/accounts/rotate-token/", {"refresh": tokens["refresh"]}, format="json")
        response = view(request)
        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh" in response.data

