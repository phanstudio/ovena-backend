import requests
from django.conf import settings
from .base import BaseRoutingBackend

class MapboxBackend(BaseRoutingBackend):
    name = "mapbox"

    def __init__(self):
        self.token = settings.MAPBOX_ACCESS_TOKEN

    def get_distance_km(self, start: tuple, end: tuple) -> float:
        lat1, lon1 = start
        lat2, lon2 = end

        coords = f"{lon1},{lat1};{lon2},{lat2}"
        resp = requests.get(
            f"https://api.mapbox.com/directions/v5/mapbox/driving/{coords}",
            params={"access_token": self.token, "geometries": "geojson"},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        metres = data["routes"][0]["distance"]
        return round(metres / 1000, 3)