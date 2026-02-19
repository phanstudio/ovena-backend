from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.generics import GenericAPIView
from ..serializers import ouput_serializers  as otS
from ..models import (
    Menu, MenuItem,
    Business, Branch, BaseItemAvailability, Order,
)
from ..pagifications import StandardResultsSetPagination

from accounts.models import LinkedStaff, User
from authflow.decorators import subuser_authentication
from authflow.permissions import ScopePermission, ReadScopePermission

import logging
from django.db.models import OuterRef, Subquery, IntegerField, Avg, Count, Q
from django.contrib.gis.db.models.functions import Distance
from addresses.utils import resolve_user_point
from django.db.models.functions import Coalesce

logger = logging.getLogger(__name__)


# add a defualt branch with is the main or first branch of the resurant
# auhentication for the resturant view
class RestaurantView(APIView):
    def get(self, request):
        businesses = Business.objects.prefetch_related(
            "menus__categories__items__variant_groups__options",
            "menus__categories__items__addon_groups__addons",
            "menus__categories__items__branch_availabilities",
        )
        serializer = otS.BusinessSerializer(businesses, many=True)
        return Response(serializer.data)

class TopBranchesView(APIView):
    def get(self, request):
        top_branches = Branch.objects.annotate(
            avg_rating=Avg('branch_ratings_received__stars'),
            rating_count=Count('branch_ratings_received')
        ).select_related("business"
        ).filter(
            rating_count__gt=0
        ).order_by('-avg_rating', '-rating_count')[:10]
        serializer = otS.TopBranchSerilazer(top_branches, many=True)
        return Response({'data': serializer.data})

class MenuView(APIView):
    def get(self, request, business_id):
        menus = Menu.objects.filter(business_id=business_id)\
                            .prefetch_related("categories__items")
        serializer = otS.MenuSerializer(menus, many=True)
        return Response(serializer.data)

# how to test searching 
class SearchMenuItems(APIView):# the search should show the restorunt the menu item came from 
    def get(self, request):
        query = request.query_params.get("q", "") # add is active? and is available
        items = MenuItem.objects.filter(
            Q(custom_name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query) |
            Q(category__menu__business__business_name__icontains=query)
        ).select_related("category__menu__business")

        serializer = otS.MenuItemSerializer(items, many=True)
        return Response(serializer.data)

# # we need to be able to get the a list of the menus, and the resturants, 
# # we need perform proper searching whether wth caching and other techniques
# # we search by categories resturants and so on?


# we want reviews associated to the branches and resturants
# we get restrants 
# top picks
# recently visited
class HomePageView(APIView):
    def get(self, request):
        user_point = resolve_user_point(request)
        if not user_point:
            return Response(
                {"detail": "Provide current location (lat,lng) or set a default address with a location."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        nearest_branch_qs = (
            Branch.objects
            .filter(
                business_id=OuterRef("pk"),
                is_active=True,
                is_accepting_orders=True,
                location__isnull=False,
            )
            .annotate(dist=Distance("location", user_point))
            .order_by("dist")
        )

        # this gives us all the closeby returants period

        businesses = (
            Business.objects
            .annotate(nearest_branch_id=Subquery(nearest_branch_qs.values("id")[:1]))
            .annotate(nearest_branch_distance=Subquery(nearest_branch_qs.values("dist")[:1]))
            .filter(nearest_branch_id__isnull=False)
            .order_by("nearest_branch_distance")
        )

        # If homepage must include full menu nesting, keep your prefetch (heavy):
        businesses = businesses.prefetch_related(
            "menus__categories__items__variant_groups__options",
            "menus__categories__items__addon_groups__addons",
            # "menus__categories__items__branch_availabilities",
        )

        # Bulk fetch nearest branches (NO N+1)
        branch_ids = [r.nearest_branch_id for r in businesses]
        branches_by_id = Branch.objects.in_bulk(branch_ids)

        serializer = otS.BusinessSerializer(
            businesses,
            many=True,
            context={
                "branches_by_id": branches_by_id,
                "user_point": user_point,
            },
        )

        # for one customer: last time they ordered from each restaurant
        last_order_qs = (
            Order.objects
            .filter(
                orderer=request.user.customer_profile,
                branch__business_id=OuterRef("pk"),
            )
            .exclude(status="cancelled")               # optional
            .order_by("-created_at")
        )

        recent_businesses = (
            Business.objects
            .annotate(last_order_at=Subquery(last_order_qs.values("created_at")[:1]))
            .filter(last_order_at__isnull=False)
            .order_by("-last_order_at")[:10]
        )

        recent_serializer = otS.BusinessSerializer(
            recent_businesses,
            many=True,
        )

        top_branch_qs = (
            Branch.objects
            .filter(business_id=OuterRef("pk"), is_active=True, is_accepting_orders=True)
            .order_by("-rating_sum", "-rating_count", "id")
        )

        top_businesses = (
            Business.objects
            .annotate(top_branch_id=Subquery(top_branch_qs.values("id")[:1]))
            .annotate(top_branch_sum=Coalesce(Subquery(top_branch_qs.values("rating_sum")[:1]), 0, output_field=IntegerField()))
            .annotate(top_branch_count=Coalesce(Subquery(top_branch_qs.values("rating_count")[:1]), 0, output_field=IntegerField()))
            .order_by("-top_branch_sum", "-top_branch_count", "id")
        )

        top_serializer = otS.BusinessSerializer(
            top_businesses,
            many=True,
        )


        return Response({
            "nearby": serializer.data,
            "top_picks": top_serializer.data,
            "recently_visited": recent_serializer.data
        })


# # another for getting the other resturants
# # the same resturants

# class UsersActivites(APIView):
#     def post(self, request):
#         # send all the users info as thime passes 
#         # if the user order add that 
#         pass


    # orderer = models.ForeignKey(CustomerProfile, on_delete= models.CASCADE, related_name="orders")
    # branch = models.ForeignKey(Branch, on_delete= models.CASCADE, related_name= "orders")
    # # delivery_price = models.DecimalField(decimal_places= 5, max_digits= 10, default= 0)
    # # ovena_commision = models.DecimalField(max_digits=5, decimal_places=2, default= 10)
    # coupons = models.ForeignKey(Coupons, on_delete= models.CASCADE, related_name= "coupons", blank=True, null= True)

    # # status = models.CharField(max_length= 30, choices= STATUS_CHOICES, default= "pending")

# who is this for the user before payment is made, the payment gatway has been made no pyment is made yet so we need to kill that transaction
# custom authentication with select related for this, we need paginification here
# finished

def norm_name(s: str) -> str:
    return (s or "").strip().casefold()

def get_branch_staff(user):
    branch:Branch = None
    error = None
    if isinstance(user, LinkedStaff):
        branch = user.created_by.branch
    elif isinstance(user, User):
        branch = user.primaryagent.branch
    else:
        error = Response(
            {"detail": "user is not a resturant employee"},
            status=status.HTTP_404_NOT_FOUND,
        )
    return branch, error

@subuser_authentication
class AvaliabilityView(GenericAPIView): # not sure if it wil be this direct sha must likely not be
    queryset = BaseItemAvailability.objects.all()
    permission_classes=[ScopePermission, ReadScopePermission]
    pagination_class=StandardResultsSetPagination
    required_scopes = ["item:availability"]

    def patch(self, request):
        user = self.request.user
        is_available = request.data.get("is_available") # should be a bool
        base_item_id = request.data.get("base_item_id")

        if base_item_id is None:
            return Response({"detail": "base_item_id is required"}, status=400)
        if not isinstance(is_available, bool):
            return Response({"detail": "is_available must be a boolean"}, status=400)

        branch = None
        branch, error = get_branch_staff(user)
        if error:
            return error

        updated = (
            self.get_queryset()
            .filter(branch=branch, base_item_id=base_item_id)
            .update(is_available=is_available)
        )

        if not updated:
            return Response(
                {"detail": "Item availability not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {"detail": "Availability updated", "is_available": is_available},
            status=status.HTTP_200_OK,
        )
