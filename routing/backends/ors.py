import requests
from django.conf import settings
from .base import BaseRoutingBackend

class ORSBackend(BaseRoutingBackend):
    name = "ors"

    def __init__(self):
        self.base_url = settings.ORS_BASE_URL  # local or VPS or hosted
        self.api_key = getattr(settings, "ORS_API_KEY", "")

    def get_distance_km(self, start: tuple, end: tuple) -> float:
        lat1, lon1 = start
        lat2, lon2 = end

        if self.api_key == "":
            raise ImportError("No api key")

        headers = {
            'Accept': 'application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8',
        }
        url = f"{self.base_url}/v2/directions/driving-car"
        
        resp = requests.get(
            f"{url}?api_key={self.api_key}&start={lon1},{lat1}&end={lon2},{lat2}", 
            headers=headers, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        metres = data["features"][0]["properties"]["summary"]["distance"]
        return round(metres / 1000, 3)