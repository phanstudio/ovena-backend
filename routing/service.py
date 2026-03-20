import logging
from typing import List
from django.conf import settings
from .backends.ors import ORSBackend
from .backends.mapbox import MapboxBackend
from .backends.google import GoogleBackend
from .backends.base import BaseRoutingBackend

logger = logging.getLogger(__name__)

REGISTRY = {
    "ors":     ORSBackend,
    "orsvps":  ORSBackend,   # same class, different env vars point to VPS
    "mapbox":  MapboxBackend,
    "google":  GoogleBackend,
}

def _build_backends() -> List[BaseRoutingBackend]:
    """Build backend instances from ROUTING_BACKENDS setting."""
    names = getattr(settings, "ROUTING_BACKENDS", ["ors"])
    backends = []
    for name in names:
        cls = REGISTRY.get(name)
        if cls:
            backends.append(cls())
        else:
            logger.warning(f"Unknown routing backend: {name}")
    return backends

def get_distance_km(start: tuple, end: tuple) -> float:
    """
    start/end: (lat, lon)
    Tries each backend in order. Falls back to next on failure.
    Raises RuntimeError if all fail.
    """
    backends = _build_backends()
    last_error = None

    for backend in backends:
        try:
            distance = backend.get_distance_km(start, end)
            logger.debug(f"[routing] {backend.name} → {distance} km")
            return distance
        except Exception as e:
            logger.warning(f"[routing] {backend.name} failed: {e}")
            last_error = e
            continue

    raise RuntimeError(
        f"All routing backends failed. Last error: {last_error}"
    )