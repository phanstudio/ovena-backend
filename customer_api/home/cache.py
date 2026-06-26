from django.core.cache import cache

class IDListCache:
    """
    Stores ONLY id lists. No TTL — Celery beat owns freshness (see tasks.py).
    Section objects build/parse the key; this stays dumb on purpose.
    """

    @staticmethod
    def get(key: str):
        return cache.get(key)  # None if missing/never built

    @staticmethod
    def set(key: str, ids: list):
        cache.set(key, ids, timeout=None)

    @staticmethod
    def prepend(key: str, business_id: int):
        """Optimistic append-on-subscribe path."""
        ids = cache.get(key) or []
        if business_id not in ids:
            cache.set(key, [business_id, *ids], timeout=None)