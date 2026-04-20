from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.generics import GenericAPIView
from ..serializers import OpS, InS
from ..models import (
    Menu,
    MenuItem,
    Branch,
    BaseItemAvailability,
)
from menu.pagifications import StandardResultsSetPagination

from accounts.models import User
from authflow.permissions import IsBusinessAdmin, IsBusinessStaff
from authflow.authentication import CustomBAdminAuth, CustomBStaffAuth
from django.db import transaction
from business_api.views import AbstractBuStAdBranchView

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
# class MenuView(APIView):
#     authentication_classes=[CustomBAdminAuth]
#     permission_classes=[IsBusinessAdmin]
#     def get(self, request):
#         user = request.user.business_admin

#         menus = Menu.objects.filter(business_id=user.business_id)\
#             .prefetch_related(
#                 "categories__items__variant_groups__options",
#                 "categories__items__addon_groups__addons",
#         )
#         serializer = OpS.MenuSerializer(menus, many=True)
#         return Response(serializer.data)


class BusinessMenuView(APIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def get_user(self, request):
        return request.user.business_admin

    def get_branch(self, request, user):
        branch_id = request.query_params.get("branch")

        if branch_id:
            return Branch.objects.filter(id=branch_id, business=user.business).first()

        return None

    def get_business_id(self, user):
        return user.business_id

    def get(self, request):
        user = self.get_user(request)
        branch = self.get_branch(request, user)

        menus = Menu.objects.filter(
            business_id=self.get_business_id(user)
        ).prefetch_related(
            "categories__items__variant_groups__options",
            "categories__items__addon_groups__addons",
        )

        serializer = OpS.BusinessMenuSerializer(
            menus, many=True, context={"branch": branch}
        )

        return Response(serializer.data)


class BusinessStaffMenuView(BusinessMenuView):
    authentication_classes = [CustomBStaffAuth]
    permission_classes = [IsBusinessStaff]

    def get_user(self, request):
        return request.user.primary_agent

    def get_branch(self, request, user):
        return user.branch

    def get_business_id(self, user):
        return user.branch.business_id


# branch thing;
# how to test searching
class SearchMenuItems(
    APIView
):  # the search should show the restorunt the menu item came from
    def get(self, request):
        query = request.query_params.get("q", "")  # add is active? and is available
        items = MenuItem.objects.filter(
            Q(custom_name__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
            | Q(category__menu__business__business_name__icontains=query)
        ).select_related("category__menu__business")

        serializer = OpS.MenuItemSerializer(items, many=True)
        return Response(serializer.data)


class BaseBuisStaffAPIView(GenericAPIView):
    authentication_classes = [CustomBStaffAuth]
    permission_classes = [IsBusinessStaff]

    # def get_buisnessadmn(self, request):
    #     profile = request.user.buisnessadmin
    #     if not profile:
    #         profile = get_object_or_404(BusinessAdmin, user=request.user)
    #     return profile

    def get_branch_staff(self, request):
        user = request.user
        branch: Branch = None
        error = None
        if isinstance(user, User):
            branch = user.primary_agent.branch
        else:
            error = Response(
                {"detail": "user is not a resturant employee"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return branch, error


# not sure if it wil be this direct sha must likely not be
class AvailabilityListView(AbstractBuStAdBranchView):
    serializer_class = InS.ItemAvailabilityListSerializer
    pagination_class = StandardResultsSetPagination

    def get(self, request, *args, **kwargs):
        queryset = BaseItemAvailability.objects.filter(
            branch=self.branch
        ).select_related("base_item")

        # -------------------
        # FILTER: availability
        # -------------------
        is_available = request.query_params.get("available")
        if is_available is not None:
            queryset = queryset.filter(is_available=is_available.lower() == "true")

        # -------------------
        # FILTER: search (name)
        # -------------------
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(base_item__name__icontains=search)

        # -------------------
        # FILTER: category
        # -------------------
        category = request.query_params.get("category")
        if category:
            category_ids = [int(c) for c in category.split(",")]

            queryset = queryset.filter(
                base_item__menu_items__category_id__in=category_ids
            ).distinct()

        # -------------------
        # ORDERING
        # -------------------
        queryset = queryset.order_by("base_item__name")

        # -------------------
        # PAGINATION
        # -------------------
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page or queryset, many=True)

        if page is not None:
            return self.get_paginated_response(serializer.data)

        return Response(serializer.data)


class AvaliabilityView(AbstractBuStAdBranchView):
    queryset = BaseItemAvailability.objects.all()
    serializer_class = InS.BulkItemAvailabilityUpdateSerializer

    def patch(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        items = serializer.validated_data["items"]

        base_item_ids = [item["id"] for item in items]

        availabilities = BaseItemAvailability.objects.filter(
            branch=self.branch, base_item_id__in=base_item_ids
        )

        availability_map = {a.base_item_id: a for a in availabilities}

        updated_objects = []

        for item in items:
            obj = availability_map.get(item["id"])
            if obj:
                obj.is_available = item["is_available"]
                updated_objects.append(obj)

        with transaction.atomic():
            BaseItemAvailability.objects.bulk_update(updated_objects, ["is_available"])

        return Response(
            {
                "detail": "Bulk availability updated",
                "updated_count": len(updated_objects),
            }
        )
