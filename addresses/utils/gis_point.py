from django.contrib.gis.geos import Point

def make_point(lon, lat, srid=4326):
    return Point(lon, lat, srid=srid)

def checkset_location(branch_data, long:str = "longitude", lat: str = "latitude"):
    long = branch_data.get(long, None)
    lat  = branch_data.get(lat, None)
    return make_point(long, lat) if long is None and lat is None else None
