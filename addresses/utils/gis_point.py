from django.contrib.gis.geos import Point

def make_point(lon, lat, srid=4326):
    return Point(lon, lat, srid=srid)
