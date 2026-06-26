from abc import ABC, abstractmethod

class HomeSection(ABC):
    """
    A homepage block. The view never queries directly — it always
    goes through .get(region, ctx). Cacheable sections hit the cache
    first; non-cacheable ones (recently_viewed) always compute live.
    """
    key_name: str           # e.g. "carousel" — used in cache key + response key
    serializer_class = None
    is_cacheable = True
    limit = 10
    base_qs = None

    def cache_key(self, region: str) -> str:
        return f"home:{self.key_name}:{region}"

    @abstractmethod
    def fetch_ids(self, region: str, ctx: dict) -> list[int]:
        """Cold-path query. Used by Celery rebuild AND as fallback on cache miss."""
        ...

    def get_ids(self, region: str, ctx: dict, cache_backend) -> list[int]:
        if not self.is_cacheable:
            return self.fetch_ids(region, ctx)

        ids = None#cache_backend.get(self.cache_key(region))
        if ids is None:
            # cold start / never rebuilt yet — compute once, let Celery own it after
            ids = self.fetch_ids(region, ctx)
            cache_backend.set(self.cache_key(region), ids)
        return ids