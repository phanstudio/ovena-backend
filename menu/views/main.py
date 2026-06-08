# logger = logging.getLogger(__name__)

# # add a defualt branch with is the main or first branch of the resurant
# # auhentication for the resturant view

# # # we need to be able to get the a list of the menus, and the resturants, 
# # # we need perform proper searching whether wth caching and other techniques
# # # we search by categories resturants and so on?

# # # another for getting the other resturants
# # # the same resturants

# # who is this for the user before payment is made, the payment gatway has been made no pyment is made yet so we need to kill that transaction
# # custom authentication with select related for this, we need paginification here
# # finished

# views.py
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.db.models import OuterRef, Subquery, Prefetch, Q
from ..models import (
    Business, Branch, MenuItem, BaseItemAvailability
)
from ..serializers.menu import (
    BusinessListSerializer,
    BusinessFeaturedSerializer,
    BusinessWithMenuNamesSerializer,
    BusinessDetailSerializer,
)

from common.customer.view import BaseCustomerAPIView
from collections import OrderedDict
from abc import ABC, abstractmethod


from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.db.models import OuterRef, Subquery
from rest_framework.response import Response
from rest_framework import status
from django.db.models import F, FloatField, ExpressionWrapper
from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import timedelta



class BusinessPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50


# ============================================================================
# SHARED HELPERS
# ============================================================================


def nearest_branch_subquery(user_point, max_km=15):
    return (
        Branch.objects
        .filter(
            business_id=OuterRef("pk"),
            is_active=True,
            is_accepting_orders=True,
            location__isnull=False,
            location__distance_lte=(user_point, D(km=max_km)),
        )
        .annotate(dist=Distance("location", user_point))
        .order_by("dist")
    )


def annotate_with_nearest_branch(qs, user_point, max_km=15):
    branch_qs = nearest_branch_subquery(user_point, max_km)

    return qs.annotate(
        nearest_branch_id=Subquery(branch_qs.values("id")[:1]),
        nearest_branch_distance=Subquery(branch_qs.values("dist")[:1]),
    )


def bulk_load_branches(businesses):
    branch_ids = [
        b.nearest_branch_id for b in businesses
        if getattr(b, "nearest_branch_id", None)
    ]

    if not branch_ids:
        return {}

    return {
        b.id: b
        for b in Branch.objects.filter(id__in=branch_ids)
    }


def annotate_business_metrics(qs, user_point):
    branch_qs = nearest_branch_subquery(user_point)

    return qs.annotate(
        # nearest branch
        nearest_branch_id=Subquery(branch_qs.values("id")[:1]),
        nearest_branch_distance=Subquery(branch_qs.values("dist")[:1]),

        # rating signal
        # avg_rating=Avg("branches__ratings__value"), # was conflicting and was removed

        # demand signal (orders in last 30 days)
        order_count_30d=Count(
            "branches__orders",
            filter=Q(branches__orders__created_at__gte=timezone.now() - timedelta(days=30))
        ),

        # # lifetime popularity (smoothed)
        # total_orders=Count("branches__orders"),
    )


def apply_top_picks_ranking(qs):
    return qs.annotate(
        top_pick_score=ExpressionWrapper(
            (F("avg_rating") * 0.4) +
            (F("order_count_30d") * 0.4) +
            #(F("total_orders") * 0.1) -
            - (F("nearest_branch_distance") * 0.1),
            output_field=FloatField()
        )
    )


class LocationProviderMixin(ABC):
    @abstractmethod
    def get_user_point(self, request):
        pass

    @abstractmethod
    def get_point_error(self):
        pass

    def point_error(self) -> Response:
        return Response(
            {"detail": self.get_point_error()},
            status=status.HTTP_400_BAD_REQUEST,
        )


class LocationDependantMixin(LocationProviderMixin):
    def get_user_point(self, request):
        lat = request.query_params.get('lat')
        lng = request.query_params.get('lng')
        if not lat or not lng:
            return None
        return Point(float(lng), float(lat), srid=4326)
    
    def get_point_error(self):
        return "No location sent, either (longitude or latitude) is missing or incorrect."


class AddressDependantMixin(LocationProviderMixin):
    def get_user_point(self, request):
        profile = self.get_customer_profile(request)
        if not profile.default_address or not profile.default_address.location:
            return None
        return profile.default_address.location
    
    def get_point_error(self):
        return "No default address location set."


# ======================================================================
# VIEW
# ======================================================================

class HomePageView(LocationDependantMixin, BaseCustomerAPIView):

    def get(self, request):
        user_point = self.get_user_point(request)

        if not user_point:
            return self.point_error()

        base_qs = annotate_business_metrics(
            Business.objects.all(),
            user_point
        )

        # ---------------- TOP PICKS (SMART RANKING) ----------------
        top_picks = list(
            apply_top_picks_ranking(base_qs)
            .filter(nearest_branch_id__isnull=False)
            .order_by("-top_pick_score")[:10]
        )

        # ---------------- FEATURED (NEARBY) ----------------
        featured_businesses = list(
            base_qs
            .filter(nearest_branch_id__isnull=False)
            .order_by("nearest_branch_distance")[:10]
        )

        # ---------------- RECENT ----------------
        recently_viewed_ids = request.session.get("recently_viewed", [])[:10]

        recently_viewed = (
            list(base_qs.filter(id__in=recently_viewed_ids))
            if recently_viewed_ids else []
        )

        # ---------------- BRANCHES ----------------
        all_businesses = top_picks + featured_businesses + recently_viewed
        branches_by_id = bulk_load_branches(all_businesses)

        context = {"branches_by_id": branches_by_id}

        return Response({
            "top_picks": BusinessListSerializer(
                top_picks, many=True, context=context
            ).data,

            "featured": BusinessFeaturedSerializer(
                featured_businesses, many=True, context=context
            ).data,

            "recently_viewed": BusinessListSerializer(
                recently_viewed, many=True, context=context
            ).data,
        })
##


# ============================================================================
# BUSINESS LIST — Infinite Scroll (ultra-lightweight)
# ============================================================================
# add is closed #attention
class BusinessListView(LocationDependantMixin, APIView):
    """
    GET /businesses/?lat=&lng=&page=
    2 queries per page.
    """

    def get(self, request):
        user_point = self.get_user_point(request)
        if not user_point:
            return self.point_error()

        businesses = (
            annotate_with_nearest_branch(Business.objects.all(), user_point)
            .order_by("nearest_branch_distance")
        )

        paginator = BusinessPagination()
        page = paginator.paginate_queryset(businesses, request)

        branches_by_id = bulk_load_branches(page)

        serializer = BusinessListSerializer(
            page, many=True, context={"branches_by_id": branches_by_id}
        )
        return paginator.get_paginated_response(serializer.data)


# ============================================================================
# BUSINESS LIST WITH MENU NAMES — No addons/variants
# ============================================================================

class BusinessListWithMenuNamesView(LocationDependantMixin, APIView):
    """
    GET /businesses/with-menus/?lat=&lng=&page=
    ~5 queries per page (business + branches + menus + categories + items)
    """

    def get(self, request):
        user_point = self.get_user_point(request)
        if not user_point:
            return self.point_error()

        businesses = (
            annotate_with_nearest_branch(Business.objects.all(), user_point)
            .prefetch_related('menus__categories__items')  # No variants/addons
            .order_by("nearest_branch_distance")
        )

        paginator = BusinessPagination()
        page = paginator.paginate_queryset(businesses, request)

        branches_by_id = bulk_load_branches(page)

        serializer = BusinessWithMenuNamesSerializer(
            page, many=True, context={"branches_by_id": branches_by_id}
        )
        return paginator.get_paginated_response(serializer.data)


# ============================================================================
# SEARCH & FILTER
# ============================================================================

class BusinessSearchView(LocationDependantMixin, GenericAPIView):
    """
    GET /businesses/search/?lat=&lng=&q=&type=&min_rating=&max_distance=&page=

    Search across:
      - business_name
      - menu item names  
      - menu category names

    Filter by:
      - business_type
      - min_rating
      - max_distance (km)
    """
    pagination_class = BusinessPagination

    def get(self, request):
        user_point = self.get_user_point(request)
        if not user_point:
            return self.point_error()

        query = request.query_params.get('q', '').strip()
        business_type = request.query_params.get('type', '').strip()
        min_rating = request.query_params.get('min_rating')
        max_distance = float(request.query_params.get('max_distance', 15))

        businesses = annotate_with_nearest_branch(
            Business.objects.all(), user_point, max_km=max_distance
        )

        # SEARCH
        if query:
            businesses = businesses.filter(
                Q(business_name__icontains=query) |
                Q(menus__categories__items__custom_name__icontains=query) |
                Q(menus__categories__name__icontains=query)
            ).distinct()

        # FILTERS
        if business_type:
            businesses = businesses.filter(business_type=business_type)

        if min_rating:
            businesses = businesses.filter(avg_rating__gte=float(min_rating))

        businesses = businesses.order_by("nearest_branch_distance")

        # paginator = BusinessPagination()
        page = self.paginate_queryset(businesses)
        # page = paginator.paginate_queryset(businesses, request)

        branches_by_id = bulk_load_branches(page)

        serializer = BusinessListSerializer(
            page, many=True, context={"branches_by_id": branches_by_id}
        )
        # return paginator.get_paginated_response(serializer.data)
        return self.get_paginated_response(serializer.data)


# ============================================================================
# BUSINESS DETAIL — Full menu, branch-aware pricing
# cachable but avalability is updated;
# ============================================================================

class BusinessDetailView(LocationDependantMixin,APIView):
    """
    GET /businesses/<id>/?lat=&lng=
    - Full menu with variants and addons
    - Branch-aware: shows correct price + availability for user's nearest branch
    - Tracks recently viewed in session
    - Queries: ~6-8 (optimized)
    """
    
    def get(self, request, business_id):
        user_point = self.get_user_point(request)

        if not user_point:
            return self.point_error()
        
        try:
            business = (
                Business.objects
                .prefetch_related(
                    # Optimize MenuItem prefetch with select_related for base_item
                    Prefetch(
                        'menus__categories__items',
                        queryset=MenuItem.objects.select_related('base_item')
                    ),
                    'menus__categories__items__variant_groups__options',
                    'menus__categories__items__addon_groups__addons__base_item',
                )
                .get(id=business_id)
            )
        except Business.DoesNotExist:
            return Response(
                {"error": "Business not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Early return if business not ready
        if not business.onboarding_complete:
            return Response(
                {"error": "Business is not available yet"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        branch, distance, availability_map = self._get_branch_context(
            business_id, user_point
        )
        
        # Track recently viewed
        self._track_recently_viewed(request, business_id)
        
        serializer = BusinessDetailSerializer(
            business,
            context={
                "branch": branch,
                "distance": distance,
                "availability_map": availability_map,
            }
        )
        return Response(serializer.data)
    
    def _get_branch_context(self, business_id, user_point):
        """
        Find nearest active branch and get availability map.
        Returns: (branch, distance, availability_map)
        """
        if not user_point:
            return None, None, {}
        
        # Find nearest active branch
        branch = (
            Branch.objects
            .filter(
                business_id=business_id,  # Direct ID comparison
                is_active=True,
                is_accepting_orders=True,
                location__isnull=False,
            )
            .annotate(distance=Distance("location", user_point))
            .only('id', 'business_id')  # Minimal fields
            .order_by("distance")
            .first()
        )
        
                
        if not branch:
            return None, None, {}
        
        distance = branch.distance
        
        # Fetch all availability overrides for this branch
        availability_map = {
            av.base_item_id: av
            for av in BaseItemAvailability.objects.filter(
                branch_id=branch.id
            ).select_related('base_item')
        }
        
        return branch, distance, availability_map
    
    def _track_recently_viewed(self, request, business_id):
        """Track recently viewed businesses in session."""
        recently_viewed = request.session.get('recently_viewed', [])
        
        # Only modify session if business_id is new
        if business_id not in recently_viewed:
            recently_viewed.insert(0, business_id)
            request.session['recently_viewed'] = recently_viewed[:20]
