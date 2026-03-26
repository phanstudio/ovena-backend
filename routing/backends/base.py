from abc import ABC, abstractmethod

class BaseRoutingBackend(ABC):
    name: str = ""

    @abstractmethod
    def get_distance_km(self, start: tuple, end: tuple) -> float:
        """
        start/end: (lat, lon)
        returns: distance in km
        """
        pass