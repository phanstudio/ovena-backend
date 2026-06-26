from celery import shared_task
from .sections.registry import HOME_SECTIONS
from .cache import IDListCache

ACTIVE_REGIONS = ["NG", "GH", "KE"]  # wherever you actually operate

@shared_task
def rebuild_home_caches():
    for section in HOME_SECTIONS:
        if not section.is_cacheable:
            continue
        for region in ACTIVE_REGIONS:
            ids = section.fetch_ids(region, ctx={})
            IDListCache.set(section.cache_key(region), ids)