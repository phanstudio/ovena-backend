from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D

from django.db import models
from django.utils import timezone

class Address(gis_models.Model):
    address = gis_models.CharField(max_length=255, blank=True, null=True)  # human-readable
    location = gis_models.PointField(
        geography=True, 
        srid=4326,  # WGS 84 (standard lat/lon)
        default=Point(0.0, 0.0, srid=4326)
    )
    label = gis_models.CharField(max_length=50, blank=True, null=True)  # e.g. Home, Work
    created_at = gis_models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            gis_models.Index(fields=['location']),  # spatial index for fast distance queries
        ]

    def __str__(self):
        return f"{self.label or ''} - {self.address or 'Unknown'} : {self.location}"

    # --- Helper methods for GIS queries ---

    @staticmethod
    def nearest_to(point, limit=5):
        """
        Return nearest addresses to a given Point
        :param point: GEOS Point (lon, lat)
        :param limit: max results
        """
        return Address.objects.annotate(
            distance=Distance('location', point)
        ).order_by('distance')[:limit]

    @staticmethod
    def within_radius(point, km=5):
        """
        Return addresses within a radius (km) from a given Point
        """
        return Address.objects.filter(
            location__distance_lte=(point, D(km=km))
        ).annotate(
            distance=Distance('location', point)
        ).order_by('distance')


class DriverLocation(gis_models.Model):
    """Real-time driver GPS tracking"""
    driver = models.OneToOneField('accounts.DriverProfile', on_delete=models.CASCADE, related_name='location')
    location = gis_models.PointField(geography=True, srid=4326)
    
    # Movement data
    heading = models.FloatField(default=0, help_text="Bearing in degrees (0-360)")
    speed = models.FloatField(default=0, help_text="Speed in km/h")
    accuracy = models.FloatField(default=0, help_text="Accuracy in meters")
    
    # Status
    is_online = models.BooleanField(default=False)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            gis_models.Index(fields=['location']),
            models.Index(fields=['is_online', 'last_updated']),
        ]
    
    def __str__(self):
        return f"{self.driver.user.username} @ {self.location}"
    
    @classmethod
    def find_nearest_drivers(cls, point, radius_km=5, limit=10):
        """Find nearest available drivers within radius"""
        stale_threshold = timezone.now() - timezone.timedelta(seconds=300)
        
        return cls.objects.filter(
            is_online=True,
            last_updated__gte=stale_threshold,
            driver__is_available=True,
            location__distance_lte=(point, D(km=radius_km))
        ).annotate(
            distance=Distance('location', point)
        ).order_by('distance')[:limit]


