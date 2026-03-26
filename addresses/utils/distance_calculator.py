from django.contrib.gis.geos import Point
import math
from routing.service import get_distance_km

def resolve_user_point(request):
    """
    Priority:
    1) current location in query params (lat/lng)
    2) user's default_address location
    """
    # 1) current location from client
    lat = request.query_params.get("lat")
    lng = request.query_params.get("lng")
    if lat is not None and lng is not None:
        try:
            return Point(float(lng), float(lat), srid=4326)
        except (TypeError, ValueError):
            pass  # fall through to default address

    # 2) default address
    user = request.user
    profile = getattr(user, "customer_profile", None)
    if not profile or not profile.default_address:
        return None

    addr = profile.default_address

    # Option A: Address has PointField named "location"
    if hasattr(addr, "location") and addr.location:
        # ensure SRID is 4326
        if addr.location.srid != 4326:
            addr.location.srid = 4326
        return addr.location
    
    return None

def haversine_distance_km(point1, point2):
    """
    point1, point2: GEOS Point (lon, lat)
    returns distance in KM
    """
    lon1, lat1 = point1.x, point1.y
    lon2, lat2 = point2.x, point2.y

    # convert to radians
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])

    # formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))

    earth_radius_km = 6371
    return c * earth_radius_km

def get_distance_km_from_2points(user_point:Point, branch_point:Point):
    """
        user_point = user.customer_profile.default_address.location\n
        branch_point = branch.location
    """
    lon1, lat1 = user_point.x, user_point.y
    lon2, lat2 = branch_point.x, branch_point.y
    try:
        return get_distance_km((lon1, lat1), (lon2, lat2))
    except Exception as _:
        return haversine_distance_km(user_point, branch_point)
