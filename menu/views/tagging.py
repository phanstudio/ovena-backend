from django.shortcuts import get_object_or_404
from menu.models.categories import GlobalTag, TagGroup
from accounts.models import Business
from menu.models import MenuCategory
from menu.services.tagging import (
    suggest_tags_for_business, find_new_tag_candidates
)
from admin_api.views import BaseAppAdminAPIView
from rest_framework.generics import (
    DestroyAPIView, ListAPIView, RetrieveUpdateDestroyAPIView, ListCreateAPIView
)
from rest_framework.response import Response
from rest_framework import status
from menu.serializers.input_ser.categories import (
    CategoryTagsUpdateSerializer, GlobalTagCreateSerializer,
    TagGroupSerializer, GlobalTagSerializer, CategorySearchInputSerializer
)
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from customer_api.views import BaseCustomerAPIView
from menu.views.main import LocationDependantMixin
from collections import defaultdict
from django.db.models import Exists, OuterRef

from menu.utils.helper import (
    annotate_with_nearest_branch,
    bulk_load_branches,
    get_hours,
    is_branch_hours_open,
)


class BusinessTagSuggestionsView(BaseAppAdminAPIView):
    """
    GET /businesses/<business_id>/tag-suggestions/

    Returns every category for the business with current + suggested
    tags, in one payload, so the admin can review/edit the whole
    business's categories together.
    """
    def get(self, request, business_id):
        business = get_object_or_404(Business, pk=business_id)

        threshold = float(request.GET.get("threshold", 0.5))
        limit = int(request.GET.get("limit", 3))

        data = suggest_tags_for_business(business, threshold=threshold, limit=limit)
        return Response(
            {"business_id": business.id, "categories": data},
            status=status.HTTP_200_OK,
        )


class CategoryTagsUpdateView(BaseAppAdminAPIView):
    """
    POST /categories/<category_id>/tags/
    Body: {"tag_ids": [1, 4, 7]}

    Admin's final decision after reviewing suggestions. Fully replaces
    the category's tag set in one call — ids left out are removed,
    new ids are added.
    """
    serializer_class = CategoryTagsUpdateSerializer
    def post(self, request, category_id):
        
        category = get_object_or_404(MenuCategory, pk=category_id)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        tags = GlobalTag.objects.filter(id__in=vd["tag_ids"])
        category.global_tags.set(tags)  # clean replace: handles add + remove together

        return Response({
                "category_id": category.id,
                "tags": list(category.global_tags.values("id", "name")),
            },
            status=status.HTTP_200_OK,
        )


class GlobalTagCreateView(BaseAppAdminAPIView):# change to a bulk create
    """
    POST /tags/
    Body: {"name": "Vegan"}

    For the "no good match, create a new tag" case in the admin flow.
    """
    serializer_class = GlobalTagCreateSerializer
    def post(self, request):
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        tag, created = GlobalTag.objects.get_or_create(
            name__iexact=vd["name"],
            defaults={"name": vd["name"]},
        )
        return Response(
            {"id": tag.id, "name": tag.name, "created": created},
            status=status.HTTP_200_OK,
        )


class NewTagSuggestionsView(BaseAppAdminAPIView):
    """
    GET /tags/new-tag-suggestions/?threshold=0.5&min_usage=2

    Platform-wide gap finder: category names in real use that don't
    match any GlobalTag yet, clustered and ranked by usage so the
    admin can see "these N businesses all have a 'Suya' category and
    there's no tag for it" and decide whether to promote it.
    Pair with GlobalTagCreateView to actually create the accepted ones.
    """
    def get(self, request):
        threshold = float(request.GET.get("threshold", 0.5))
        min_usage = int(request.GET.get("min_usage", 1))
        candidates = find_new_tag_candidates(threshold=threshold, min_usage=min_usage)
        return Response(
            {"candidates": candidates},
            status=status.HTTP_200_OK,
        )


class TagGroupListCreateView(BaseAppAdminAPIView, ListCreateAPIView):
    queryset = TagGroup.objects.prefetch_related("tags").all()
    serializer_class = TagGroupSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]


class TagGroupDetailView(BaseAppAdminAPIView, RetrieveUpdateDestroyAPIView):
    queryset = TagGroup.objects.prefetch_related("tags").all()
    serializer_class = TagGroupSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]


class GlobalTagListView(BaseAppAdminAPIView, ListAPIView):
    queryset = GlobalTag.objects.select_related("group").all()
    serializer_class = GlobalTagSerializer


class GlobalTagDeleteView(BaseAppAdminAPIView, DestroyAPIView):
    queryset = GlobalTag.objects.all()
    serializer_class = GlobalTagSerializer


class TagGroupListView(BaseCustomerAPIView, ListAPIView):
    queryset = TagGroup.objects.select_related("group").all()
    serializer_class = TagGroupSerializer


class CategorySearchView(LocationDependantMixin, BaseCustomerAPIView):
    serializer_class = CategorySearchInputSerializer
    def post(self, request):
        user_point = self.get_user_point(request)
        if not user_point:
            return self.point_error()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        category_id = vd["category_id"]
        max_distance = vd["max_distance"]

        # 1. Businesses that are in range AND have at least one category
        #    matching the requested tag group. Exists() avoids the row
        #    duplication you'd get from joining straight through the
        #    global_tags M2M.
        matching_category_exists = Exists(
            MenuCategory.objects.filter(
                menu__business_id=OuterRef("pk"),
                global_tags__group_id=category_id,
            )
        )

        base_qs = annotate_with_nearest_branch(
            Business.objects.filter(is_active=True),
            user_point,
            max_km=max_distance,
        ).filter(
            nearest_branch_id__isnull=False,
        ).filter(
            matching_category_exists,
        ).order_by("nearest_branch_distance")

        # 2. Paginate at the BUSINESS level. One page = N businesses,
        #    each carrying its own nested list of matching categories.
        page = self.paginate_queryset(base_qs)
        businesses = page if page is not None else list(base_qs)
        business_ids = [b.id for b in businesses]

        if not business_ids:
            empty = []
            return (
                self.get_paginated_response(empty)
                if page is not None
                else Response(empty)
            )

        # 3. Second, targeted query: only pull categories for the
        #    businesses on THIS page, then group them in Python.
        #    Same shape as get_menu_matches_for_businesses in helper.py.
        categories = (
            MenuCategory.objects
            .filter(
                menu__business_id__in=business_ids,
                global_tags__group_id=category_id,
            )
            .select_related("menu__business")
            .distinct()
            .order_by("menu__business_id", "sort_order")
        )

        categories_by_business = defaultdict(list)
        for cat in categories:
            categories_by_business[cat.menu.business_id].append(cat)

        # 4. Bulk load today's branch hours for this page's businesses
        #    (reuses the helper you already have).
        branches_by_id = bulk_load_branches(businesses)

        # 5. Assemble the response.
        results = []
        for business in businesses:
            branch = branches_by_id.get(business.nearest_branch_id)
            hours = get_hours(branch) if branch else None

            results.append({
                "id": business.id,
                "business_name": business.business_name,
                "nearest_branch": {
                    "id": branch.id,
                    "distance_km": round(business.nearest_branch_distance.km, 2)
                        if business.nearest_branch_distance else None,
                    "is_open": is_branch_hours_open(hours),
                } if branch else None,
                "categories": [
                    {"id": c.id, "name": c.name}
                    for c in categories_by_business.get(business.id, [])
                ],
            })

        return (
            self.get_paginated_response(results)
            if page is not None
            else Response(results)
        )
