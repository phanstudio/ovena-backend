from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.generics import GenericAPIView
# from rest_framework.permissions import AllowAny
from ..serializers import OpS
from ..models import (
    Menu, MenuItem,
    Business, Branch, BaseItemAvailability,
)
from ..pagifications import StandardResultsSetPagination

from accounts.models import LinkedStaff, User
from authflow.decorators import subuser_authentication
from authflow.permissions import ScopePermission, ReadScopePermission, IsBusinessAdmin
from authflow.authentication import CustomBAdminAuth

import logging
from django.db.models import Q

logger = logging.getLogger(__name__)

# for later on the branch level ie the person is a business staff
# from django.db.models import Prefetch

# branch = ...  # get from request

# menus = Menu.objects.filter(business_id=user.id).prefetch_related(
#     "categories__items__variant_groups__options",
#     "categories__items__addon_groups__addons",
#     Prefetch(
#         "categories__items__base_item__item_availabilities",
#         queryset=BaseItemAvailability.objects.filter(branch=branch),
#         to_attr="filtered_availability"
#     )
# )
class MenuView(APIView):
    authentication_classes=[CustomBAdminAuth]
    permission_classes=[IsBusinessAdmin]
    def get(self, request):
        user = request.user.business_admin
        
        menus = Menu.objects.filter(business_id=user.business_id)\
            .prefetch_related(
                "categories__items__variant_groups__options",
                "categories__items__addon_groups__addons",
        )
        serializer = OpS.MenuSerializer(menus, many=True)
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

        serializer = OpS.MenuItemSerializer(items, many=True)
        return Response(serializer.data)

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
