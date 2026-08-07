from django.core.cache import cache
from rest_framework_simplejwt.settings import api_settings

SUSPENSION_TTL = int(api_settings.ACCESS_TOKEN_LIFETIME.total_seconds())  # e.g. 900

def _key(user_id):
    return f"driver:suspended:{user_id}"

def is_suspended(user_id) -> bool:
    val = cache.get(_key(user_id))
    if val is not None:
        return val
    return False

def set_suspended(user_id, value: bool):
    cache.set(_key(user_id), value, SUSPENSION_TTL)

def clear_suspension_cache(user_id):
    cache.delete(_key(user_id))