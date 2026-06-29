from accounts.models import Business, BusinessSubscription
from menu.utils.helper import (
    annotate_business_metrics, apply_top_picks_ranking, annotate_subscription_tiers, DailyRotationMixin
)
from .base import HomeSection
from menu.serializers.menu import (
    BusinessListSerializer, BusinessFeaturedSerializer, BusinessBannerSerializer, BusinessCarouselSerializer
)
from payments.models.subscription import Subscription
import random
from authflow.features import BANNER, CAROUSEL
from django.db.models import Exists, OuterRef

#:new
# admin can select how the sub is linked to the parts for eg; in the code we just check if the plan is attched to this feature??
# the feature being the banner or the 
# we need to add random sufful

# class BannerSection(HomeSection):
#     """1 slot. Subscription tier = 'banner'."""
#     key_name = BANNER
#     serializer_class = BusinessBannerSerializer
#     limit = 1
#     base_qs = BusinessSubscription.objects.all()
    
#     def fetch_ids(self, region, ctx):
#         subscribed_users = Subscription.objects.filter(
#             plan__features__code=BANNER,
#             active=True,
#         ).values("user_id")
        
#         return list(
#             Business.objects.filter(
#                 onboarding_complete=True,
#                 admin__user_id__in=subscribed_users,
#             ).values_list("id", flat=True)[: self.limit]
#         )


# class CarouselSection(HomeSection):
#     """N slots. Same mechanism as banner, different tier — see note below."""
#     key_name = CAROUSEL
#     serializer_class = BusinessCarouselSerializer
#     limit = 5

#     def fetch_ids(self, region, ctx):
#         active_sub = Subscription.objects.filter(
#             user_id=OuterRef("admin__user_id"),
#             plan__features__code=CAROUSEL,
#             active=True,
#         )

#         return list(
#             Business.objects.annotate(
#                 has_carousel=Exists(active_sub)
#             ).filter(
#                 onboarding_complete=True,
#                 has_carousel=True,
#             ).values_list("id", flat=True)[: self.limit]
#         )


class BannerSection(DailyRotationMixin, HomeSection):
    """1 slot. Subscription tier = 'banner'. Rotates daily."""
    key_name = BANNER
    serializer_class = BusinessBannerSerializer
    limit = 1
    base_qs = BusinessSubscription.objects.all()

    def fetch_ids(self, region, ctx):
        active_sub = Subscription.objects.filter(
            user_id=OuterRef("admin__user_id"),
            plan__features__code=BANNER,
            active=True,
        )

        qs = Business.objects.annotate(
            has_banner=Exists(active_sub)
        ).filter(
            onboarding_complete=True,
            has_banner=True,
        )

        # Apply daily rotation before slicing
        rotated_qs = self.apply_daily_rotation(qs)
        
        return list(rotated_qs.values_list("id", flat=True)[: self.limit])


class CarouselSection(DailyRotationMixin, HomeSection):
    """N slots. Subscription tier = 'carousel'. Rotates daily."""
    key_name = CAROUSEL
    serializer_class = BusinessCarouselSerializer
    limit = 5
    base_qs = BusinessSubscription.objects.all()

    def fetch_ids(self, region, ctx):
        active_sub = Subscription.objects.filter(
            user_id=OuterRef("admin__user_id"),
            plan__features__code=CAROUSEL,
            active=True,
        )

        qs = Business.objects.annotate(
            has_carousel=Exists(active_sub)
        ).filter(
            onboarding_complete=True,
            has_carousel=True,
        )

        # Apply daily rotation before slicing
        rotated_qs = self.apply_daily_rotation(qs)
        
        return list(rotated_qs.values_list("id", flat=True)[: self.limit])


class FeaturedSection(HomeSection):
    """Nearby, NOT subscription-driven — depends on user_point, so cacheable
    only at a coarse region level, not truly personalized."""
    key_name = "featured"
    serializer_class = BusinessFeaturedSerializer
    is_cacheable = False  # distance-sorted = per-request; don't cache IDs here

    def fetch_ids(self, region, ctx):
        user_point = ctx["user_point"]
        base_qs = annotate_business_metrics(Business.objects.all(), user_point)
        return list(
            base_qs.filter(nearest_branch_id__isnull=False)
            .order_by("nearest_branch_distance")
            .values_list("id", flat=True)[: self.limit]
        )


# class TopPickSection(HomeSection):
#     """Global ranking per region — see assumption flagged above."""
#     key_name = "top_pick"
#     serializer_class = BusinessListSerializer
#     limit = 10

#     def fetch_ids(self, region, ctx):
#         user_point = ctx["user_point"]
#         base_qs = annotate_business_metrics(Business.objects.all(), user_point)
#         ranked = (
#             apply_top_picks_ranking(base_qs)
#             .filter(nearest_branch_id__isnull=False, country=region)
#             .order_by("-top_pick_score")
#         )
#         return list(ranked.values_list("id", flat=True)[: self.limit])


class TopPickSection(HomeSection):
    key_name = "top_pick"
    serializer_class = BusinessListSerializer
    limit = 10
    TOP_SLOTS = 3

    def fetch_ids(self, region, ctx):
        user_point = ctx["user_point"]

        base_qs = annotate_business_metrics(Business.objects.all(), user_point)
        base_qs = annotate_subscription_tiers(base_qs)

        ranked = apply_top_picks_ranking(base_qs).filter(
            nearest_branch_id__isnull=False, #country=region
        )

        # businesses entitled to a guaranteed top-3 slot, randomized each rebuild
        top3_ids = list(ranked.filter(has_top3=True).values_list("id", flat=True))
        random.shuffle(top3_ids)
        top3_ids = top3_ids[: self.TOP_SLOTS]

        remaining_slots = self.limit - len(top3_ids)
        rest_ids = list(
            ranked.exclude(id__in=top3_ids)
            .order_by("-top_pick_score")
            .values_list("id", flat=True)[:remaining_slots]
        )

        return top3_ids + rest_ids


class RecentlyViewedSection(HomeSection):
    """Per-user, session-backed. Never cached, never region-keyed."""
    key_name = "recently_viewed"
    serializer_class = BusinessListSerializer
    is_cacheable = False
    limit = 10

    def fetch_ids(self, region, ctx):
        return ctx["request"].session.get("recently_viewed", [])[: self.limit]
