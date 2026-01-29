"""
GIS utilities for driver matching and distance calculations
Place in: drivers/gis_utils.py
"""
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.utils import timezone
from django.conf import settings
from addresses.models import DriverLocation
import math
# from menu.gis_utils2 import *

def calculate_distance(point1, point2):
    """
    Calculate distance between two points in kilometers
    :param point1: Point(longitude, latitude)
    :param point2: Point(longitude, latitude)
    :return: Distance in kilometers
    """
    # Use geodesic distance (accounts for Earth's curvature)
    from geopy.distance import geodesic
    
    coords1 = (point1.y, point1.x)  # (lat, lon)
    coords2 = (point2.y, point2.x)
    
    return geodesic(coords1, coords2).kilometers


def calculate_eta(distance_km, avg_speed_kmh=30):
    """
    Calculate estimated time of arrival
    :param distance_km: Distance in kilometers
    :param avg_speed_kmh: Average speed (default 30 km/h for city traffic)
    :return: ETA in minutes
    """
    hours = distance_km / avg_speed_kmh
    minutes = hours * 60
    return int(minutes)


def find_nearest_available_drivers(branch_location, max_drivers=3):
    """
    Find nearest available drivers using expanding radius search
    
    :param branch_location: Point object of branch location
    :param max_drivers: Maximum number of drivers to return
    :return: List of (driver_profile, distance_km) tuples
    """
    stale_threshold = timezone.now() - timezone.timedelta(
        seconds=settings.DRIVER_LOCATION_STALE_THRESHOLD
    )
    
    search_radiuses = settings.DRIVER_SEARCH_RADIUS_KM  # [5, 10, 15]
    
    # Try expanding radiuses
    for radius in search_radiuses:
        drivers = DriverLocation.objects.filter(
            is_online=True,
            last_updated__gte=stale_threshold,
            driver__is_available=True,
            driver__current_order__isnull=True,
            location__distance_lte=(branch_location, D(km=radius))
        ).select_related('driver', 'driver__user').annotate(
            distance=Distance('location', branch_location)
        ).order_by('distance')[:max_drivers]
        
        if drivers.exists():
            return [
                (d.driver, d.distance.km) 
                for d in drivers
            ]
    
    # If no drivers found in radiuses, get nearest overall
    drivers = DriverLocation.objects.filter(
        is_online=True,
        last_updated__gte=stale_threshold,
        driver__is_available=True,
        driver__current_order__isnull=True,
    ).select_related('driver', 'driver__user').annotate(
        distance=Distance('location', branch_location)
    ).order_by('distance')[:max_drivers]

    drivers = list(drivers)
    if drivers:
    # if drivers.exists():
        return [
            (d.driver, d.distance.km)
            for d in drivers
        ]
    
    return []


def calculate_delivery_fee(distance_km, base_fee=500, per_km_fee=100):
    """
    Calculate delivery fee based on distance
    
    :param distance_km: Distance in kilometers
    :param base_fee: Base delivery fee in smallest currency unit (kobo for Naira)
    :param per_km_fee: Fee per kilometer
    :return: Total delivery fee in kobo
    """
    # Base fee + distance-based fee
    total_fee = base_fee + (distance_km * per_km_fee)
    
    # Round to nearest 50 kobo
    return round(total_fee / 50) * 50


def is_driver_near_location(driver_location, target_point, threshold_km=0.5):
    """
    Check if driver is near a location (for pickup/delivery confirmation)
    
    :param driver_location: DriverLocation object
    :param target_point: Point to check against
    :param threshold_km: Distance threshold in km (default 500 meters)
    :return: Boolean
    """
    distance = calculate_distance(driver_location.location, target_point)
    return distance <= threshold_km


def get_driver_current_location(driver):
    """
    Get driver's current location if available and recent
    
    :param driver: DriverProfile object
    :return: DriverLocation object or None
    """
    try:
        location = driver.location
        stale_threshold = timezone.now() - timezone.timedelta(
            seconds=settings.DRIVER_LOCATION_STALE_THRESHOLD
        )
        
        if location.last_updated >= stale_threshold:
            return location
    except DriverLocation.DoesNotExist:
        pass
    
    return None


def calculate_bearing(point1, point2):
    """
    Calculate bearing (heading) between two points
    
    :param point1: Starting Point
    :param point2: Destination Point
    :return: Bearing in degrees (0-360)
    """
    lat1 = math.radians(point1.y)
    lat2 = math.radians(point2.y)
    diff_long = math.radians(point2.x - point1.x)
    
    x = math.sin(diff_long) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (
        math.sin(lat1) * math.cos(lat2) * math.cos(diff_long)
    )
    
    initial_bearing = math.atan2(x, y)
    initial_bearing = math.degrees(initial_bearing)
    compass_bearing = (initial_bearing + 360) % 360
    
    return compass_bearing


def validate_coordinates(lat, lng):
    """
    Validate latitude and longitude values
    
    :param lat: Latitude
    :param lng: Longitude
    :return: Boolean
    """
    try:
        lat = float(lat)
        lng = float(lng)
        
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return True
    except (ValueError, TypeError):
        pass
    
    return False


def geocode_address(address_string):
    """
    Convert address string to coordinates (optional - requires API key)
    
    :param address_string: Address to geocode
    :return: Point object or None
    """
    from geopy.geocoders import Nominatim
    
    try:
        geolocator = Nominatim(user_agent="ovena_delivery")
        location = geolocator.geocode(address_string)
        
        if location:
            return Point(location.longitude, location.latitude, srid=4326)
    except Exception as e:
        print(f"Geocoding error: {e}")
    
    return None


def reverse_geocode_point(point):
    """
    Convert coordinates to address string (optional - requires API key)
    
    :param point: Point object
    :return: Address string or None
    """
    from geopy.geocoders import Nominatim
    
    try:
        geolocator = Nominatim(user_agent="ovena_delivery")
        location = geolocator.reverse(f"{point.y}, {point.x}")
        
        if location:
            return location.address
    except Exception as e:
        print(f"Reverse geocoding error: {e}")
    
    return None


# ===== HELPER FOR DELIVERY RADIUS VALIDATION =====

def is_location_in_service_area(location, service_areas):
    """
    Check if location is within any service area polygon
    Useful for limiting delivery zones
    
    :param location: Point object
    :param service_areas: List of Polygon objects
    :return: Boolean
    """
    from django.contrib.gis.geos import Polygon
    
    for area in service_areas:
        if isinstance(area, Polygon) and area.contains(location):
            return True
    
    return False