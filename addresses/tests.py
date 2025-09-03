import pytest
from .utils.gis_point import make_point
from addresses.models import Address
from django.contrib.gis.db.models.functions import Distance

@pytest.mark.django_db
class TestAddressGIS:

    @pytest.fixture(autouse=True)
    def setup_addresses(self):
        """Create sample addresses at known coordinates"""
        self.london = Address.objects.create(
            address="10 Downing St",
            location=make_point(-0.1278, 51.5074),
            label="Home"
        )
        self.paris = Address.objects.create(
            address="Eiffel Tower",
            location=make_point(2.2945, 48.8584),
            label="Landmark"
        )
        self.nyc = Address.objects.create(
            address="Times Square",
            location=make_point(-73.9857, 40.7580),
            label="Tourist"
        )

    def test_nearest_to(self):
        """nearest_to should return addresses ordered by distance"""
        user_location = make_point(-0.12, 51.50)  # near London

        nearest = Address.nearest_to(user_location, limit=2)

        print(nearest)
        assert len(nearest) == 2
        assert nearest[0].label == "Home"      # London closest
        assert nearest[1].label == "Landmark"  # Paris second

    def test_within_radius(self):
        """within_radius returns only addresses within given km"""
        user_location = make_point(-0.12, 51.50)

        nearby = Address.within_radius(user_location, km=350)  # London-Paris < 350km
        labels = [addr.label for addr in nearby]

        print(nearby)

        assert "Home" in labels
        assert "Landmark" in labels
        assert "Tourist" not in labels  # NYC too far

    def test_distance_annotation(self):
        """Distance annotation should produce numeric distances in meters"""
        user_location = make_point(-0.12, 51.50)

        annotated = Address.objects.annotate(
            distance=Distance('location', user_location)
        ).order_by('distance')

        print(vars(annotated))
        print(annotated)

        assert annotated[0].label == "Home"
        assert annotated[0].distance.m > 0
        assert annotated[1].distance.m > annotated[0].distance.m
