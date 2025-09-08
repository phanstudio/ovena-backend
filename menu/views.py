from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .serializers import ouput_serializers  as otS
from .serializers import input_serializers as InS
from .models import (
    Menu, MenuCategory, MenuItem, VariantGroup, VariantOption, 
    MenuItemAddonGroup, MenuItemAddon, MenuItemAvailability, 
    Restaurant, Branch
)

from django.db.models import Q

class RestaurantView(APIView):
    def get(self, request):
        restaurants = Restaurant.objects.prefetch_related(
            "menus__categories__items__variant_groups__options",
            "menus__categories__items__addon_groups__addons",
            "menus__categories__items__branch_availabilities",
        )
        serializer = otS.RestaurantSerializer(restaurants, many=True)
        return Response(serializer.data)

class MenuView(APIView):
    def get(self, request, restaurant_id):
        menus = Menu.objects.filter(restaurant_id=restaurant_id)\
                            .prefetch_related("categories__items")
        serializer = otS.MenuSerializer(menus, many=True)
        return Response(serializer.data)

class SearchMenuItems(APIView):
    def get(self, request):
        query = request.query_params.get("q", "")
        items = MenuItem.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query) |
            Q(category__menu__restaurant__company_name__icontains=query)
        ).select_related("category__menu__restaurant")

        serializer = otS.MenuItemSerializer(items, many=True)
        return Response(serializer.data)



# # we need to be able to get the a list of the menus, and the resturants, 
# # we need perform proper searching whether wth caching and other techniques
# # we search by categories resturants and so on?
# class Menu(APIView):
#     def get(self, request):
#         self.categories() # might not be needed
#         pass
    
#     def categories(self): # not sure if this is needed or just get from the resturants
#         MenuCategory.objects.all()
#         pass

#     # we want to get the resturant for the menus
#     # list the menus and allow searching ?

# class HomepageView(APIView):
#     def get(self, request):
#         restaurants = Restaurant.objects.prefetch_related(
#             "menus__categories__items__variant_groups__options",
#             "menus__categories__items__addon_groups__addons",
#             "menus__categories__items__branch_availabilities",
#         )
#         # get top categories
#         # recently visited resturants, empty 
#         # top picks # best rated resturants
#         # pagification for the resturant 

#         serializer = RestaurantSerializer(restaurants, many=True)
#         return Response(serializer.data)

# # another for getting the other resturants
# # the same resturants

# class UsersActivites(APIView):
#     def post(self, request):
#         # send all the users info as thime passes 
#         # if the user order add that 
#         pass

# class Orders(): # history is completed, and is active
#     pass

# manual registery
class MenuRegistrationView(APIView):
    """
    Register menus for an existing restaurant.
    JSON payload includes menus, categories, items, variants, addons, availabilities.
    """

    def post(self, request):
        restaurant_id = request.data.get("restaurant_id")
        if not restaurant_id:
            return Response({"detail": "restaurant_id is required"}, status=400)

        try:
            restaurant = Restaurant.objects.get(pk=restaurant_id)
        except Restaurant.DoesNotExist:
            return Response({"detail": "Restaurant not found"}, status=404)
        
        menus_data = request.data.get("menus", [])

        created_menus = []

        for menu_data in menus_data:
            # Validate with serializer
            serializer = InS.MenuSerializer(data=menu_data)
            serializer.is_valid(raise_exception=True)

            # Create menu
            menu = Menu.objects.create(
                restaurant=restaurant,
                name=serializer.validated_data["name"],
                description=serializer.validated_data.get("description", ""),
                is_active=serializer.validated_data.get("is_active", True),
            )

            # Loop categories
            for cat_data in serializer.validated_data["categories"]:
                category = MenuCategory.objects.create(
                    menu=menu,
                    name=cat_data["name"],
                    sort_order=cat_data.get("sort_order", 0),
                )

                # Prepare items for this category
                for item_data in cat_data["items"]:
                    item = MenuItem.objects.create(
                        category=category,
                        name=item_data["name"],
                        description=item_data.get("description", ""),
                        price=item_data["price"],
                        image=item_data.get("image", None),
                    )

                    # === Variant groups + options (bulk for options)
                    for vg_data in item_data.get("variant_groups", []):
                        vg = VariantGroup.objects.create(
                            item=item,
                            name=vg_data["name"],
                            is_required=vg_data.get("is_required", True),
                        )

                        options = [
                            VariantOption(
                                group=vg,
                                name=opt["name"],
                                price_diff=opt.get("price_diff", 0),
                            )
                            for opt in vg_data.get("options", [])
                        ]
                        VariantOption.objects.bulk_create(options)

                    # === Addon groups + addons (bulk for addons)
                    for ag_data in item_data.get("addon_groups", []):
                        ag = MenuItemAddonGroup.objects.create(
                            item=item,
                            name=ag_data["name"],
                            is_required=ag_data.get("is_required", False),
                            max_selection=ag_data.get("max_selection", 0),
                        )

                        addons = [
                            MenuItemAddon(
                                group=ag,
                                name=addon["name"],
                                price=addon["price"],
                            )
                            for addon in ag_data.get("addons", [])
                        ]
                        MenuItemAddon.objects.bulk_create(addons)

                    # === Collect existing availability objects to update
                    updates = []
                    for av_data in item_data.get("availabilities", []):
                        try:
                            branch = Branch.objects.get(name=av_data["branch"])
                        except Branch.DoesNotExist:
                            continue

                        obj = MenuItemAvailability.objects.filter(branch=branch, item=item).first()
                        if obj:
                            new_is_available = av_data.get("is_available", obj.is_available)
                            new_override = av_data.get("override_price", obj.override_price)

                            if obj.is_available != new_is_available or obj.override_price != new_override:
                                obj.is_available = new_is_available
                                obj.override_price = new_override
                                updates.append(obj)

                    # Bulk update fields
                    if updates:
                        MenuItemAvailability.objects.bulk_update(updates, ["is_available", "override_price"])

            created_menus.append(menu.id)

        return Response(
            {"message": "Menus registered successfully", "menus": created_menus, "company_name": restaurant.company_name},
            status=status.HTTP_201_CREATED,
        )
