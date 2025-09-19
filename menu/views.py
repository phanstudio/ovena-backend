from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.generics import UpdateAPIView, ListAPIView, GenericAPIView
from rest_framework.mixins import ListModelMixin, CreateModelMixin, UpdateModelMixin
from .serializers import ouput_serializers  as otS
from .serializers import input_serializers as InS
from .models import (
    Menu, MenuCategory, MenuItem, VariantGroup, VariantOption, 
    MenuItemAddonGroup, MenuItemAddon, BaseItem, 
    Restaurant, Branch, BaseItemAvailability, 
    Order
)
from accounts.models import LinkedStaff, User
from django.db.models import Q
from authflow.decorators import subuser_authentication
from authflow.authentication import CustomJWTAuthentication
from authflow.permissions import ScopePermission, ReadScopePermission
from .pagifications import StandardResultsSetPagination

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

# how to test searching 
class SearchMenuItems(APIView):# the search should show the restorunt the menu item came from 
    def get(self, request):
        query = request.query_params.get("q", "") # add is active? and is available
        items = MenuItem.objects.filter(
            Q(custom_name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query) |
            Q(category__menu__restaurant__company_name__icontains=query)
        ).select_related("category__menu__restaurant")

        serializer = otS.MenuItemSerializer(items, many=True)
        return Response(serializer.data)

# # we need to be able to get the a list of the menus, and the resturants, 
# # we need perform proper searching whether wth caching and other techniques
# # we search by categories resturants and so on?

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

class OrderView(APIView, ListModelMixin, CreateModelMixin, UpdateModelMixin):
    # list all the orders the person has made
    # create a model
    # update the progres of the order
    # check your progress
    # cancle order
    pass

@subuser_authentication
class ResturantOrderView(GenericAPIView):
    permission_classes=[ScopePermission, ReadScopePermission]
    pagination_class=StandardResultsSetPagination
    required_scopes = ["order:accept", "order:cancle"]
    # and move them to seperate functions but this way is lighter i think?

    def get_queryset(self):
        user = self.request.user
        
        # LinkedStaff (sub token)
        if isinstance(user, LinkedStaff):
            return Order.objects.filter(branch=user.created_by.branch)

        # LinkedStaff (sub token)
        if isinstance(user, User):
            return Order.objects.filter(branch=user.primaryagent.branch)

        return Order.objects.none()

    def get(self, request, *args, **kwargs):
        qs = self.get_queryset().values(
            "id", "status", "created_at",
            "items__id", "items__menu_item_id", "items__quantity", "items__price"
        )
        page = self.paginate_queryset(qs)
        self.pagination_class()
        return self.get_paginated_response(list(page))

    def post(self, request):
        action = request.data.get("action")
        order_id = request.data.get("order_id")

        if not action or action not in ["accept", "cancle", "made"]:
            return Response({"error": "Action required"}, status=status.HTTP_400_BAD_REQUEST)
        
        order = self.get_queryset().filter(id=order_id).first()
        if not order:
            return Response(
                {"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND
            )
        
        if action == "accept":
            return self.accept_order(order)
        elif action == "made":
            return self.order_made(order)
        else:
            return self.cancle_order(order)

    def accept_order(self, order: Order): # updates the user and the driver # with consumers or something simular
        if order.status != "pending":
            return Response(
                {"error": "Order already accepted"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = "confirmed"
        order.save(update_fields=["status"])
        # TODO: trigger driver notification here
        return Response(
            {"message": "Order accepted successfully"},
            status=status.HTTP_202_ACCEPTED,
        )

    def order_made(self, order: Order): # change this or move to the driver
        if order.status != "confirmed":
            return Response(
                {"error": "Order must be confirmed first"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = "ready"
        order.save(update_fields=["status"])
        return Response(
            {"message": "Order marked as ready"},
            status=status.HTTP_200_OK,
        )

    def cancle_order(self, order: Order): # send request to the drivers and user
        if order.status in ["delivered", "ready"]: # use not in confirmed and pending after thta not the resturants buisnes again
            return Response(
                {"error": "Cannot cancel after order is ready/delivered"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = "cancelled"
        order.save(update_fields=["status"])
        return Response(
            {"message": "Order cancelled successfully"},
            status=status.HTTP_200_OK,
        )

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

                # Items under this category
                for item_data in cat_data["items"]:
                    # === Create or reuse BaseItem
                    base_item, _ = BaseItem.objects.get_or_create(
                        name=item_data["base_item"]["name"],
                        defaults={
                            "description": item_data["base_item"].get("description", ""),
                            "default_price": item_data["base_item"]["price"],
                            "image": item_data["base_item"].get("image", None),
                        },
                    )

                    # === Wrap as MenuItem
                    item = MenuItem.objects.create(
                        category=category,
                        base_item=base_item,
                        custom_name=item_data.get("custom_name", base_item.name),
                        description=item_data.get("description", base_item.description),
                        price=item_data.get("price", base_item.default_price),
                        image=item_data.get("image", None),
                    )

                    # === Variant groups + options
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

                    # === Addon groups + addons
                    for ag_data in item_data.get("addon_groups", []):
                        ag = MenuItemAddonGroup.objects.create(
                            item=item,
                            name=ag_data["name"],
                            is_required=ag_data.get("is_required", False),
                            max_selection=ag_data.get("max_selection", 0),
                        )

                        addons = []
                        for addon in ag_data.get("addons", []):
                            # Reuse or create BaseItem for addon
                            addon_base, _ = BaseItem.objects.get_or_create(
                                name=addon["base_item"]["name"],
                                defaults={
                                    "description": addon["base_item"].get("description", ""),
                                    "default_price": addon["base_item"]["price"],
                                    "image": addon["base_item"].get("image", None),
                                },
                            )
                            addon_obj = MenuItemAddon.objects.create(
                                base_item=addon_base,
                                price=addon.get("price", addon_base.default_price),
                            )
                            addons.append(addon_obj)

                        if addons:
                            # ManyToMany relationship to group
                            for ad in addons:
                                ad.groups.add(ag)

            created_menus.append(menu.id)

        return Response(
            {
                "message": "Menus registered successfully",
                "menus": created_menus,
                "company_name": restaurant.company_name,
            },
            status=status.HTTP_201_CREATED,
        )

class AvaliabilityView(UpdateAPIView): # change availblity
    queryset = BaseItemAvailability
    # we want to check if the person s an employee of the resturant
    def patch(self, request):
        is_available = request.data.get("is_available") # true or false
        item = request.data.get("item") # base item pk
        branch = request.data.get("branch_id")# pk
        super().patch(request)



# move to branch adding and editing
# === Availability updates (BaseItemAvailability)
                    # updates = []
                    # for av_data in item_data.get("availabilities", []):
                    #     try:
                    #         branch = Branch.objects.get(name=av_data["branch"])
                    #     except Branch.DoesNotExist:
                    #         continue

                    #     obj = BaseItemAvailability.objects.filter(
                    #         branch=branch, base_item=base_item
                    #     ).first()

                    #     if obj:
                    #         new_is_available = av_data.get("is_available", obj.is_available)
                    #         new_override = av_data.get("override_price", obj.override_price)

                    #         if obj.is_available != new_is_available or obj.override_price != new_override:
                    #             obj.is_available = new_is_available
                    #             obj.override_price = new_override
                    #             updates.append(obj)

                    # if updates:
                    #     BaseItemAvailability.objects.bulk_update(
                    #         updates, ["is_available", "override_price"]
                    #     )