# logger = logging.getLogger(__name__)


# class BaseCustomerAPIView(GenericAPIView):
#     authentication_classes = [CustomCustomerAuth]
#     permission_classes = [IsCustomer]

#     def get_customer_profile(self, request) -> CustomerProfile:
#         profile = request.user.customer_profile
#         if not profile:
#             raise Http404("Customer profile not found")
#         return profile

# # add a defualt branch with is the main or first branch of the resurant
# # auhentication for the resturant view
# class RestaurantView(APIView):
#     def get(self, request):
#         businesses = Business.objects.prefetch_related(
#             "menus__categories__items__variant_groups__options",
#             "menus__categories__items__addon_groups__addons",
#             "menus__categories__items__branch_availabilities",
#         )
#         serializer = OpS.BusinessSerializer(businesses, many=True)
#         return Response(serializer.data)

# class TopBranchesView(APIView):
#     def get(self, request):
#         top_branches = Branch.objects.annotate(
#             avg_rating=Avg('branch_ratings_received__stars'),
#             rating_count=Count('branch_ratings_received')
#         ).select_related("business"
#         ).filter(
#             rating_count__gt=0
#         ).order_by('-avg_rating', '-rating_count')[:10]
#         serializer = OpS.TopBranchSerilazer(top_branches, many=True)
#         return Response({'data': serializer.data})

# class MenuView(APIView):
#     def get(self, request, business_id):
#         menus = Menu.objects.filter(business_id=business_id)\
#                             .prefetch_related("categories__items")
#         serializer = OpS.MenuSerializer(menus, many=True)
#         return Response(serializer.data)

# # how to test searching 
# class SearchMenuItems(APIView):# the search should show the restorunt the menu item came from 
#     def get(self, request):
#         query = request.query_params.get("q", "") # add is active? and is available
#         items = MenuItem.objects.filter(
#             Q(custom_name__icontains=query) |
#             Q(description__icontains=query) |
#             Q(category__name__icontains=query) |
#             Q(category__menu__business__business_name__icontains=query)
#         ).select_related("category__menu__business")

#         serializer = OpS.MenuItemSerializer(items, many=True)
#         return Response(serializer.data)

# # # we need to be able to get the a list of the menus, and the resturants, 
# # # we need perform proper searching whether wth caching and other techniques
# # # we search by categories resturants and so on?


# # we want reviews associated to the branches and resturants
# # we get restrants 
# # top picks
# # recently visited

# # # another for getting the other resturants
# # # the same resturants

# # class UsersActivites(APIView):
# #     def post(self, request):
# #         # send all the users info as thime passes 
# #         # if the user order add that 
# #         pass


#     # orderer = models.ForeignKey(CustomerProfile, on_delete= models.CASCADE, related_name="orders")
#     # branch = models.ForeignKey(Branch, on_delete= models.CASCADE, related_name= "orders")
#     # # delivery_price = models.DecimalField(decimal_places= 5, max_digits= 10, default= 0)
#     # # ovena_commision = models.DecimalField(max_digits=5, decimal_places=2, default= 10)
#     # coupons = models.ForeignKey(Coupons, on_delete= models.CASCADE, related_name= "coupons", blank=True, null= True)

#     # # status = models.CharField(max_length= 30, choices= STATUS_CHOICES, default= "pending")

# # who is this for the user before payment is made, the payment gatway has been made no pyment is made yet so we need to kill that transaction
# # custom authentication with select related for this, we need paginification here
# # finished

# views.py
from rest_framework.views import APIView
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


class BusinessPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50


# ============================================================================
# SHARED HELPERS
# ============================================================================

def get_user_point(request):
    lat = request.query_params.get('lat')
    lng = request.query_params.get('lng')
    if not lat or not lng:
        return None
    return Point(float(lng), float(lat), srid=4326)


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
    ).filter(nearest_branch_id__isnull=False)


def bulk_load_branches(businesses):
    branch_ids = [
        b.nearest_branch_id for b in businesses
        if b.nearest_branch_id
    ]
    return Branch.objects.in_bulk(branch_ids)


def build_availability_map(branch, businesses):
    """
    Load all BaseItemAvailability rows for this branch
    for all base_items under all menu items of these businesses.
    Returns: {base_item_id: BaseItemAvailability}
    One query only.
    """
    business_ids = [b.id for b in businesses]
    availabilities = BaseItemAvailability.objects.filter(
        branch=branch,
        base_item__menu_items__category__menu__business_id__in=business_ids
    ).select_related('base_item')

    return {a.base_item_id: a for a in availabilities}


# ============================================================================
# HOMEPAGE
# ============================================================================

# we will eventually add guest support but not now
class HomePageView(BaseCustomerAPIView):
    """
    Sections: top_picks, featured, recently_viewed
    Queries: ~8-10 total for all 3 sections
    """

    def get(self, request):
        profile = self.get_customer_profile(request)
        user_point = profile.default_address.location

        if not user_point:
            return Response(
                {"detail": "No default address location set."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        base_qs = annotate_with_nearest_branch(Business.objects.all(), user_point)

        # TOP PICKS
        top_picks = list(
            base_qs
            .order_by('-avg_rating', 'nearest_branch_distance')
            [:10]
        )

        featured_businesses = list(
            base_qs
            # .prefetch_related(
            #     Prefetch(
            #         'menus__categories__items',
            #         queryset=MenuItem.objects.prefetch_related(
            #             'variant_groups__options',
            #             'addon_groups__addons__base_item',
            #         )
            #     )
            # )
            .order_by('nearest_branch_distance')
            [:10]
        )

        # RECENTLY VIEWED
        recently_viewed_ids = request.session.get('recently_viewed', [])[:10]
        recently_viewed = list(
            base_qs.filter(id__in=recently_viewed_ids)
        ) if recently_viewed_ids else [] # ths looks expensive also recently visted;

        # BULK LOAD BRANCHES — one query
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




# # ============================================================================
# # SHARED HELPERS
# # ============================================================================


# def get_nearby_branches(user_point, max_km=15):
#     """
#     ONE GIS QUERY ONLY.
#     This replaces expensive correlated subqueries.
#     """

#     return (
#         Branch.objects
#         .filter(
#             is_active=True,
#             is_accepting_orders=True,
#             location__isnull=False,
#             location__distance_lte=(user_point, D(km=max_km)),
#         )
#         .annotate(
#             distance=Distance("location", user_point)
#         )
#         .select_related("business")
#         .only(
#             "id",
#             "business_id",
#             "location",
#             "is_active",
#             "is_accepting_orders",
#         )
#         .order_by("business_id", "distance")
#     )


# def build_business_maps(user_point, max_km=15):
#     """
#     Builds:
#     - nearest branch per business
#     - nearby business ids
#     - business distance map

#     ALL from one query.
#     """

#     nearby_branches = get_nearby_branches(user_point, max_km)

#     nearest_branch_by_business = OrderedDict()

#     for branch in nearby_branches:

#         # first branch encountered is nearest because
#         # queryset already ordered by distance
#         if branch.business_id not in nearest_branch_by_business:
#             nearest_branch_by_business[branch.business_id] = branch

#     business_ids = list(nearest_branch_by_business.keys())

#     return {
#         "business_ids": business_ids,
#         "branches_by_business_id": nearest_branch_by_business,
#     }


# def attach_branch_annotations(businesses, branches_by_business_id):
#     """
#     Mimic annotated fields in memory.
#     """

#     for business in businesses:

#         branch = branches_by_business_id.get(business.id)

#         if branch:
#             business.nearest_branch_id = branch.id
#             business.nearest_branch_distance = branch.distance
#         else:
#             business.nearest_branch_id = None
#             business.nearest_branch_distance = None

#     return businesses



# # ============================================================================
# # HOMEPAGE
# # ============================================================================

# class HomePageView(BaseCustomerAPIView):
#     """
#     Optimized homepage:
#     - ONE GIS query
#     - NO correlated subqueries
#     - minimal DB roundtrips
#     """

#     def get(self, request):

#         profile = self.get_customer_profile(request)

#         if not profile.default_address:
#             return Response(
#                 {"detail": "No default address set."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         user_point = profile.default_address.location

#         if not user_point:
#             return Response(
#                 {"detail": "No default address location set."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         # ====================================================================
#         # BUILD NEARBY BUSINESS MAPS
#         # ====================================================================

#         maps = build_business_maps(user_point)

#         business_ids = maps["business_ids"]

#         branches_by_business_id = maps["branches_by_business_id"]

#         # ====================================================================
#         # LOAD BUSINESSES ONCE
#         # ====================================================================

#         all_businesses = list(
#             Business.objects
#             .filter(id__in=business_ids)
#             .only(
#                 "id",
#                 "business_name",
#                 "business_logo",
#                 "avg_rating",
#             )
#         )

#         # attach nearest branch fields in memory
#         attach_branch_annotations(
#             all_businesses,
#             branches_by_business_id,
#         )

#         # quick lookup
#         business_map = {
#             b.id: b
#             for b in all_businesses
#         }

#         # ====================================================================
#         # TOP PICKS
#         # ====================================================================

#         top_picks = sorted(
#             all_businesses,
#             key=lambda b: (
#                 -(b.avg_rating or 0),
#                 float(b.nearest_branch_distance.m)
#                 if b.nearest_branch_distance
#                 else 999999
#             )
#         )[:10]

#         # ====================================================================
#         # FEATURED
#         # ====================================================================

#         featured_businesses = sorted(
#             all_businesses,
#             key=lambda b: (
#                 float(b.nearest_branch_distance.m)
#                 if b.nearest_branch_distance
#                 else 999999
#             )
#         )[:10]

#         # ====================================================================
#         # RECENTLY VIEWED
#         # ====================================================================

#         recently_viewed_ids = request.session.get(
#             "recently_viewed",
#             []
#         )[:10]

#         recently_viewed = [
#             business_map[bid]
#             for bid in recently_viewed_ids
#             if bid in business_map
#         ]

#         # ====================================================================
#         # SERIALIZER CONTEXT
#         # ====================================================================

#         context = {
#             "branches_by_business_id": branches_by_business_id,
#         }

#         return Response({
#             "top_picks": BusinessListSerializer(
#                 top_picks,
#                 many=True,
#                 context=context,
#             ).data,

#             "featured": BusinessFeaturedSerializer(
#                 featured_businesses,
#                 many=True,
#                 context=context,
#             ).data,

#             "recently_viewed": BusinessListSerializer(
#                 recently_viewed,
#                 many=True,
#                 context=context,
#             ).data,
#         })


# def get_nearest_branches_for_top_businesses(user_point, limit=100, max_km=15):
#     """
#     Get nearest branch for top N businesses by distance.
#     Uses a window function to get only the nearest branch per business.
#     """
#     from django.db.models import Window, F, RowNumber
#     from django.db.models.functions import RowNumber as RN
    
#     # Subquery approach: for each business, get ONLY the nearest branch
#     branches_with_rank = (
#         Branch.objects
#         .filter(
#             is_active=True,
#             is_accepting_orders=True,
#             location__isnull=False,
#             location__distance_lte=(user_point, D(km=max_km)),
#         )
#         .annotate(
#             distance=Distance("location", user_point),
#             rank=Window(
#                 expression=RowNumber(),
#                 partition_by=F('business_id'),
#                 order_by=F('distance').asc()
#             )
#         )
#         .filter(rank=1)  # Only nearest branch per business
#         .select_related('business')  # NOW we can select_related
#         .only(
#             "id",
#             "business_id",
#             "location",
#             "business__id",
#             "business__business_name",
#             "business__business_logo",
#             "business__avg_rating",
#         )
#         .order_by('distance')[:limit]  # Only get top 100 closest businesses
#     )
    
#     return list(branches_with_rank)


# class HomePageView(BaseCustomerAPIView):
#     def get(self, request):
#         profile = self.get_customer_profile(request)
#         user_point = profile.default_address.location

#         if not user_point:
#             return Response(
#                 {"detail": "No default address location set."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         # ================================================================
#         # GET ONLY NEAREST BRANCHES (not all branches)
#         # ================================================================
        
#         # Use DISTINCT ON to get only one branch per business
#         # PostgreSQL specific but very efficient
#         from django.db.models import OuterRef, Subquery
        
#         # Subquery to get nearest branch ID for each business
#         nearest_branch_subq = (
#             Branch.objects
#             .filter(
#                 business_id=OuterRef('pk'),
#                 is_active=True,
#                 is_accepting_orders=True,
#                 location__isnull=False,
#                 location__distance_lte=(user_point, D(km=15)),
#             )
#             .annotate(dist=Distance("location", user_point))
#             .order_by("dist")
#             .values('id')[:1]
#         )
        
#         # Annotate businesses with their nearest branch
#         base_qs = (
#             Business.objects
#             .annotate(
#                 nearest_branch_id=Subquery(nearest_branch_subq),
#                 nearest_branch_distance=Subquery(
#                     Branch.objects
#                     .filter(
#                         business_id=OuterRef('pk'),
#                         is_active=True,
#                         is_accepting_orders=True,
#                         location__isnull=False,
#                         location__distance_lte=(user_point, D(km=15)),
#                     )
#                     .annotate(dist=Distance("location", user_point))
#                     .order_by("dist")
#                     .values('dist')[:1]
#                 )
#             )
#             .filter(nearest_branch_id__isnull=False)
#             .only("id", "business_name", "business_logo", "avg_rating")
#         )
        
#         # NOW we only query for 10 at a time
#         top_picks = list(
#             base_qs.order_by('-avg_rating', 'nearest_branch_distance')[:10]
#         )
        
#         featured = list(
#             base_qs.order_by('nearest_branch_distance')[:10]
#         )
        
#         recently_viewed_ids = request.session.get("recently_viewed", [])[:10]
#         recently_viewed = list(
#             base_qs.filter(id__in=recently_viewed_ids)
#         ) if recently_viewed_ids else []
        
#         # Load actual branch objects for serialization
#         all_businesses = top_picks + featured + recently_viewed
#         branch_ids = [b.nearest_branch_id for b in all_businesses if b.nearest_branch_id]
#         branches_by_id = Branch.objects.in_bulk(branch_ids)
        
#         context = {"branches_by_id": branches_by_id}
        
#         return Response({
#             "top_picks": BusinessListSerializer(top_picks, many=True, context=context).data,
#             "featured": BusinessFeaturedSerializer(featured, many=True, context=context).data,
#             "recently_viewed": BusinessListSerializer(recently_viewed, many=True, context=context).data,
#         })


# ============================================================================
# BUSINESS LIST — Infinite Scroll (ultra-lightweight)
# ============================================================================

class BusinessListView(APIView):
    """
    GET /businesses/?lat=&lng=&page=
    2 queries per page.
    """

    def get(self, request):
        user_point = get_user_point(request)
        if not user_point:
            return Response(
                {"error": "lat and lng are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

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

class BusinessListWithMenuNamesView(APIView):
    """
    GET /businesses/with-menus/?lat=&lng=&page=
    ~5 queries per page (business + branches + menus + categories + items)
    """

    def get(self, request):
        user_point = get_user_point(request)
        if not user_point:
            return Response(
                {"error": "lat and lng are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

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

class BusinessSearchView(APIView):
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

    def get(self, request):
        user_point = get_user_point(request)
        if not user_point:
            return Response(
                {"error": "lat and lng are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

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

        paginator = BusinessPagination()
        page = paginator.paginate_queryset(businesses, request)

        branches_by_id = bulk_load_branches(page)

        serializer = BusinessListSerializer(
            page, many=True, context={"branches_by_id": branches_by_id}
        )
        return paginator.get_paginated_response(serializer.data)


# ============================================================================
# BUSINESS DETAIL — Full menu, branch-aware pricing
# ============================================================================

class BusinessDetailView(APIView):
    """
    GET /businesses/<id>/?lat=&lng=

    - Full menu with variants and addons
    - Branch-aware: shows correct price + availability for user's nearest branch
    - Tracks recently viewed in session
    - Queries: ~10-12
    """

    def get(self, request, business_id):
        user_point = get_user_point(request)

        try:
            business = (
                Business.objects
                .prefetch_related(
                    'menus__categories__items__variant_groups__options',
                    'menus__categories__items__addon_groups__addons__base_item',
                    'menus__categories__items__base_item',  # for effective_price
                )
                .get(id=business_id)
            )
        except Business.DoesNotExist:
            return Response(
                {"error": "Business not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Find nearest branch for this user
        branch = None
        distance = None
        availability_map = {}

        if user_point:
            branch = (
                Branch.objects
                .filter(
                    business=business,
                    is_active=True,
                    is_accepting_orders=True,
                    location__isnull=False,
                )
                .annotate(dist=Distance("location", user_point))
                .order_by("dist")
                .first()
            )

            if branch:
                distance = branch.dist
                # One query for all availability/price overrides for this branch
                availabilities = BaseItemAvailability.objects.filter(
                    branch=branch
                ).select_related('base_item')
                availability_map = {a.base_item_id: a for a in availabilities}

        # Track recently viewed
        recently_viewed = request.session.get('recently_viewed', [])
        if business_id not in recently_viewed:
            recently_viewed.insert(0, business_id)
            request.session['recently_viewed'] = recently_viewed[:20]

        serializer = BusinessDetailSerializer(
            business,
            context={
                "branch": branch,
                "distance": distance,
                "availability_map": availability_map,
            }
        )
        return Response(serializer.data)
