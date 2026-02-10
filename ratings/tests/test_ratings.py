import pytest

from accounts.models import User, CustomerProfile, DriverProfile, Restaurant, Branch
from menu.models import Order
from ratings.models import DriverRating, BranchRating
from ratings.services import RatingService


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def restaurant():
    return Restaurant.objects.create(
        company_name="Testaurant",
        bn_number="1234567-000",
    )


@pytest.fixture
def branch(restaurant):
    return Branch.objects.create(
        restaurant=restaurant,
        name="Main Branch",
        address="123 Test Street",
    )


@pytest.fixture
def driver_profile():
    user = User.objects.create(email="driver@example.com", name="Driver")
    return DriverProfile.objects.create(user=user)


@pytest.fixture
def customer_profile():
    user = User.objects.create(email="customer@example.com", name="Customer")
    return CustomerProfile.objects.create(user=user)


@pytest.fixture
def customer_profile_2():
    user = User.objects.create(email="customer2@example.com", name="Customer Two")
    return CustomerProfile.objects.create(user=user)


@pytest.fixture
def order(customer_profile, branch, driver_profile):
    return Order.objects.create(
        orderer=customer_profile,
        branch=branch,
        driver=driver_profile,
        delivery_secret_hash="secret",
        status="delivered",
        order_number=1,
    )


@pytest.fixture
def order_2(customer_profile_2, branch, driver_profile):
    return Order.objects.create(
        orderer=customer_profile_2,
        branch=branch,
        driver=driver_profile,
        delivery_secret_hash="secret-2",
        status="delivered",
        order_number=2,
    )


def test_driver_rating_signals_create_update_delete(order, customer_profile, driver_profile):
    rating = DriverRating.objects.create(
        order=order,
        rater=customer_profile,
        driver=driver_profile,
        stars=4,
        review="",
    )

    driver_profile.refresh_from_db()
    assert driver_profile.rating_sum == 4
    assert driver_profile.rating_count == 1
    assert driver_profile.avg_rating == 4.0

    rating.stars = 2
    rating.save()

    driver_profile.refresh_from_db()
    assert driver_profile.rating_sum == 2
    assert driver_profile.rating_count == 1
    assert driver_profile.avg_rating == 2.0

    rating.delete()

    driver_profile.refresh_from_db()
    assert driver_profile.rating_sum == 0
    assert driver_profile.rating_count == 0
    assert driver_profile.avg_rating == 0.0


def test_branch_rating_signals_create_update_delete(order, customer_profile, branch):
    rating = BranchRating.objects.create(
        order=order,
        rater=customer_profile,
        branch=branch,
        stars=5,
        review="",
    )

    branch.refresh_from_db()
    assert branch.rating_sum == 5
    assert branch.rating_count == 1
    assert branch.avg_rating == 5.0

    rating.stars = 3
    rating.save()

    branch.refresh_from_db()
    assert branch.rating_sum == 3
    assert branch.rating_count == 1
    assert branch.avg_rating == 3.0

    rating.delete()

    branch.refresh_from_db()
    assert branch.rating_sum == 0
    assert branch.rating_count == 0
    assert branch.avg_rating == 0.0


def test_rating_service_stats_and_lookup(order, order_2, customer_profile, customer_profile_2, driver_profile, branch):
    DriverRating.objects.create(
        order=order,
        rater=customer_profile,
        driver=driver_profile,
        stars=4,
    )
    DriverRating.objects.create(
        order=order_2,
        rater=customer_profile_2,
        driver=driver_profile,
        stars=2,
    )

    BranchRating.objects.create(
        order=order,
        rater=customer_profile,
        branch=branch,
        stars=5,
    )
    BranchRating.objects.create(
        order=order_2,
        rater=customer_profile_2,
        branch=branch,
        stars=3,
    )

    driver_stats = RatingService.driver_stats(driver_profile.id)
    branch_stats = RatingService.branch_stats(branch.id)

    assert driver_stats.avg == 3.0
    assert driver_stats.count == 2
    assert branch_stats.avg == 4.0
    assert branch_stats.count == 2

    ratings = RatingService.order_ratings(order.id, customer_profile.id)
    assert ratings["driver_rating"] is not None
    assert ratings["branch_rating"] is not None


def test_submit_for_order_creates_ratings(order, customer_profile, driver_profile, branch):
    results = RatingService.submit_for_order(
        order=order,
        rater=customer_profile,
        driver_payload={"stars": 5, "review": "Great"},
        branch_payload={"stars": 4, "review": "Good"},
    )

    assert results["driver_rating"].stars == 5
    assert results["branch_rating"].stars == 4

    driver_profile.refresh_from_db()
    branch.refresh_from_db()

    assert driver_profile.rating_sum == 5
    assert driver_profile.rating_count == 1
    assert driver_profile.avg_rating == 5.0

    assert branch.rating_sum == 4
    assert branch.rating_count == 1
    assert branch.avg_rating == 4.0


def test_submit_for_order_updates_driver_rating(order, customer_profile, driver_profile):
    RatingService.submit_for_order(
        order=order,
        rater=customer_profile,
        driver_payload={"stars": 5},
    )

    RatingService.submit_for_order(
        order=order,
        rater=customer_profile,
        driver_payload={"stars": 3},
    )

    driver_profile.refresh_from_db()
    assert driver_profile.rating_sum == 3
    assert driver_profile.rating_count == 1
    assert driver_profile.avg_rating == 3.0


# @pytest.mark.xfail(reason="BranchRating.clean uses driver_id; updates via submit_for_order raise AttributeError.")
def test_submit_for_order_updates_branch_rating(order, customer_profile, branch):
    RatingService.submit_for_order(
        order=order,
        rater=customer_profile,
        branch_payload={"stars": 5},
    )

    RatingService.submit_for_order(
        order=order,
        rater=customer_profile,
        branch_payload={"stars": 2},
    )

    branch.refresh_from_db()
    assert branch.rating_sum == 2
    assert branch.rating_count == 1
    assert branch.avg_rating == 2.0
