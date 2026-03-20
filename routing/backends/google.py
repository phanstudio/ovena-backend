import requests
from django.conf import settings
from .base import BaseRoutingBackend

class GoogleBackend(BaseRoutingBackend):
    name = "google"

    def __init__(self):
        self.api_key = settings.GOOGLE_MAPS_API_KEY

    def get_distance_km(self, start: tuple, end: tuple) -> float:
        lat1, lon1 = start
        lat2, lon2 = end

        resp = requests.get(
            "https://maps.googleapis.com/maps/api/distancematrix/json",
            params={
                "origins": f"{lat1},{lon1}",
                "destinations": f"{lat2},{lon2}",
                "key": self.api_key,
            },
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        metres = data["rows"][0]["elements"][0]["distance"]["value"]
        return round(metres / 1000, 3)