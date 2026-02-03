
# the verson with the simple menu retrival
# another mitegation would be to show all but get the closest to the item.
class HomepageView(APIView):
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
                restaurant_id=OuterRef("pk"),
                is_active=True,
                is_accepting_orders=True,
                location__isnull=False,
            )
            .annotate(dist=Distance("location", user_point))
            .order_by("dist")
        )

        restaurants = (
            Restaurant.objects
            .annotate(nearest_branch_id=Subquery(nearest_branch_qs.values("id")[:1]))
            .annotate(nearest_branch_distance=Subquery(nearest_branch_qs.values("dist")[:1]))
            .filter(nearest_branch_id__isnull=False)
            .order_by("nearest_branch_distance")
        )

        # If homepage must include full menu nesting, keep your prefetch (heavy):
        restaurants = restaurants.prefetch_related(
            "menus__categories__items__variant_groups__options",
            "menus__categories__items__addon_groups__addons",
            "menus__categories__items__branch_availabilities",
        )

        # Bulk fetch nearest branches (NO N+1)
        branch_ids = [r.nearest_branch_id for r in restaurants]
        branches_by_id = Branch.objects.in_bulk(branch_ids)

        serializer = otS.RestaurantSerializer(
            restaurants,
            many=True,
            context={
                "branches_by_id": branches_by_id,
                "user_point": user_point,
            },
        )
        return Response(serializer.data)

