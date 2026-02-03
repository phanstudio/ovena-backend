from django.contrib.gis.geos import Point

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
