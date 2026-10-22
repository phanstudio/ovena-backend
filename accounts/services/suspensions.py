from __future__ import annotations

from django.core.cache import cache
from rest_framework_simplejwt.settings import api_settings

SUSPENSION_TTL = int(api_settings.ACCESS_TOKEN_LIFETIME.total_seconds())  # e.g. 900


def _key(user_id: int, role: str | None = None) -> str:
    r = role.strip().lower() if role else "all"
    return f"user:suspended:{user_id}:{r}"


def is_suspended(user_id: int, role: str | None = None) -> bool:
    """
    Check if a user has an active (unlifted) suspension for a given role or account-wide.
    Checks the cache first. If cache miss, queries Suspension records from the DB and caches.
    """
    if not user_id:
        return False

    key = _key(user_id, role)
    val = cache.get(key)
    if val is not None:
        return bool(val)

    from accounts.models import Suspension

    qs = Suspension.objects.filter(user_id=user_id, lifted_at__isnull=True)
    if role:
        qs = qs.filter(role=role)

    active_suspension = qs.exists()
    cache.set(key, active_suspension, SUSPENSION_TTL)
    return active_suspension


def set_suspended(user_id: int, role: str | None = None, value: bool = True):
    key = _key(user_id, role)
    cache.set(key, value, SUSPENSION_TTL)


def clear_suspension_cache(user_id: int, role: str | None = None):
    """
    Clear cached suspension status for a user and role.
    """
    if not user_id:
        return
    if role:
        cache.delete(_key(user_id, role))
    cache.delete(_key(user_id, "all"))
    cache.delete(_key(user_id, "driver"))
    cache.delete(_key(user_id, "business_admin"))
    cache.delete(_key(user_id, "customer"))
    cache.delete(f"driver:suspended:{user_id}")
