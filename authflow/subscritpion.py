from payments.models.subscription import Feature
from django.core.cache import cache
from common.redis.feature import get_feature_redis_backend, use_redis
from django.conf import settings
import logging
from redis import Redis

logger = logging.getLogger(__name__)

FEATURE_EXPIRATION = getattr(settings, "FEATURE_EXPIRATION", 3600)
FEATURE_KEY = "plan:{}:features"

CACHE_MISS = object()
NO_REDIS = object()

# helper
def get_key(plan_id):
    return FEATURE_KEY.format(plan_id)

def check(result):
    return result not in [CACHE_MISS, NO_REDIS]


# caching
def cache_features_redis(
    plan_id,
    features,
):
    client = get_feature_redis_backend()

    if not client:
        return NO_REDIS

    key = get_key(plan_id)

    with client.pipeline(transaction=True) as pipe:
        pipe.delete(key)
        pipe.sadd(key, *features)
        pipe.expire(key, FEATURE_EXPIRATION)
        pipe.execute()

def cache_features_cache(
    plan_id,
    features,
):
    cache.set(
        get_key(plan_id),
        list(features),
        timeout=FEATURE_EXPIRATION,
    )


# get all
def get_features_client(
    client:Redis,
    plan_id,
):
    
    key = get_key(plan_id)

    features = client.smembers(key)

    if not features:
        return None

    return features

def get_features_redis(
    plan_id,
):
    client = get_feature_redis_backend()

    if not client:
        return NO_REDIS
    
    features = get_features_client(client, plan_id)

    if features is None:
        return CACHE_MISS

    return features

def get_features_cache(
    plan_id,
):
    features = cache.get(get_key(plan_id))

    if features is None:
        return CACHE_MISS  # cache miss

    return features


# checking
def has_feature_redis(
    plan_id,
    code,
):
    client = get_feature_redis_backend()

    if not client:
        return NO_REDIS

    features = get_features_client(client, plan_id)

    if features is None:
        return CACHE_MISS

    return code in features

def has_feature_cache(
    plan_id,
    code,
):
    features = get_features_cache(plan_id)

    if features is CACHE_MISS:
        return CACHE_MISS  # cache miss

    return code in features


# unified
def has_feature(
    plan_id,
    code,
):
    if use_redis():
        return has_feature_redis(
            plan_id,
            code,
        )

    return has_feature_cache(
        plan_id,
        code,
    )

def cache_features(
    plan_id,
    features,
):
    if use_redis():
        return cache_features_redis(
            plan_id,
            features,
        )

    return cache_features_cache(
        plan_id,
        features,
    )

def get_features(
    plan_id,
):

    if use_redis():
        return get_features_redis(plan_id)

    return get_features_cache(plan_id)


# export
def check_feature(plan_id, code):
    result = NO_REDIS
    try:
        result = has_feature(plan_id, code)
    except Exception as e:
        logger.exception("[Check Feature redis] request error: %s", e)

    if check(result):
        return result
    
    features = list(
        Feature.objects.filter(
            plans__id=plan_id
        ).values_list(
            "code",
            flat=True,
        )
    )

    if features:
        try:
            cache_features(plan_id, features)
        except Exception as e:
            logger.exception("[Cache Features redis] request error: %s", e)

    return code in features

def get_all_features(plan_id):
    features = NO_REDIS
    try:
        features = get_features(plan_id)
    except Exception as e:
        logger.exception("[Get Features redis] request error: %s", e)

    if check(features):
        return features
    
    features = []
    features = list(Feature.objects.filter(
        plans__id=plan_id
    ).values_list(
        "code",
        flat=True
    ))
    if features:
        try:
            cache_features(plan_id, features)
        except Exception as e:
            logger.exception("[Cache Features redis] request error: %s", e)
    return features
