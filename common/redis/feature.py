import redis
from django.conf import settings
from django.core.cache import cache

def get_feature_redis_backend():
    redis_url = getattr(
        settings,
        "FEATURE_REDIS_URL",
        None,
    )

    if not redis_url:
        return None

    return redis.from_url(
        redis_url,
        decode_responses=True,
    )


def use_redis():
    backend = getattr(
        settings,
        "FEATURE_CACHE_BACKEND",
        "auto",
    )

    if backend == "redis":
        return True

    if backend == "cache":
        return False

    # auto mode

    if get_feature_redis_backend():
        return True

    cache_backend = cache.__class__.__module__.lower()

    return (
        "redis" in cache_backend
        or "django_redis" in cache_backend
    )
