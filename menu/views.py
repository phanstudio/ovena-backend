from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.generics import GenericAPIView
# from rest_framework.mixins import ListModelMixin, CreateModelMixin, UpdateModelMixin
from .serializers import ouput_serializers  as otS
from .serializers import input_serializers as InS
from .models import (
    Menu, MenuCategory, MenuItem, VariantGroup, VariantOption, 
    MenuItemAddonGroup, MenuItemAddon, BaseItem, 
    Restaurant, Branch, BaseItemAvailability, 
    Order, Coupons
)
from accounts.models import LinkedStaff, User, Rating
from django.db.models import Q
from authflow.decorators import subuser_authentication
from authflow.authentication import CustomCustomerAuth, CustomDriverAuth
from authflow.permissions import ScopePermission, ReadScopePermission
from .pagifications import StandardResultsSetPagination
from authflow.services import generate_passphrase, hash_phrase, verify_delivery_phrase
from django.shortcuts import get_object_or_404

from paystackapi.transaction import Transaction
from django.db.models import Avg, Count

class RestaurantView(APIView):
    def get(self, request):
        restaurants = Restaurant.objects.prefetch_related(
            "menus__categories__items__variant_groups__options",
            "menus__categories__items__addon_groups__addons",
            "menus__categories__items__branch_availabilities",
        )
        serializer = otS.RestaurantSerializer(restaurants, many=True)
        return Response(serializer.data)

class TopBranchesView(APIView):
    def get(self, request):
        top_branches = Branch.objects.annotate(
            avg_rating=Avg('branch_ratings_received__stars'),
            rating_count=Count('branch_ratings_received')
        ).select_related("restaurant"
        ).filter(
            rating_count__gt=0
        ).order_by('-avg_rating', '-rating_count')[:10]
        serializer = otS.TopBranchSerilazer(top_branches, many=True)
        return Response({'data': serializer.data})

class MenuView(APIView):
    def get(self, request, restaurant_id):
        menus = Menu.objects.filter(restaurant_id=restaurant_id)\
                            .prefetch_related("categories__items")
        serializer = otS.MenuSerializer(menus, many=True)
        return Response(serializer.data)

class RateView(APIView):
    authentication_classes=[CustomCustomerAuth]
    permission_classes = [IsAuthenticated]
    def post(self, request):
        data = request.data
        user = request.user
        if not hasattr(user, "customer_profile"):
            return Response({"error": "not a cusomer"}, 403)
        
        order_id = data.get("order_id")
        rating_who = data.get("rating_who") or 0 # 0, 1, 2
        stars = data.get("stars") or 1
        review = data.get("review") or None
        complaint_type = data.get("complaint_type") # get the complaint type
        
        if not complaint_type:
            return Response({"error": "no complaint type"}, 403)

        order = Order.objects.filter(pk=order_id).first()
        if not order:
            return Response({"error": "no order passed, invalid order id"}, 403)
        
        rated_driver_id = None
        rated_branch_id = None

        if rating_who in [0, 2]:
            rated_driver_id = order.driver_id
        if rating_who in [1, 2]:
            rated_branch_id = order.branch_id

        Rating.objects.create(
            rater=user.customer_profile,
            rated_driver_id=rated_driver_id,
            rated_branch_id=rated_branch_id,
            stars=stars,
            review=review,
            complaint_type=complaint_type,
        )

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


    # orderer = models.ForeignKey(CustomerProfile, on_delete= models.CASCADE, related_name="orders")
    # branch = models.ForeignKey(Branch, on_delete= models.CASCADE, related_name= "orders")
    # # delivery_price = models.DecimalField(decimal_places= 5, max_digits= 10, default= 0)
    # # ovena_commision = models.DecimalField(max_digits=5, decimal_places=2, default= 10)
    # coupons = models.ForeignKey(Coupons, on_delete= models.CASCADE, related_name= "coupons", blank=True, null= True)

    # # status = models.CharField(max_length= 30, choices= STATUS_CHOICES, default= "pending")


# urlpatterns = [
#     path("orders/", OrderView.as_view()),
#     path("orders/<int:order_id>/", OrderView.as_view()),
# ]

# /orders/<int:order_id>/
# /orders/
class OrderView(APIView):
    authentication_classes = [CustomCustomerAuth]

    def get_queryset(self, request):
        """Return only the logged-in user's orders."""
        user = request.user
        if not hasattr(user, "customer_profile"):
            return Order.objects.none()
        return Order.objects.filter(orderer=user.customer_profile).select_related("branch", "coupons")

    # ✅ 1. LIST all orders or GET a specific one
    def get(self, request, order_id=None, *args, **kwargs): # paginification
        qs = self.get_queryset(request)

        # If order_id is passed -> get single order
        if order_id:
            order = get_object_or_404(qs, id=order_id)
            data = {
                "id": order.id,
                "status": order.status,
                "created_at": order.created_at,
                "branch": order.branch.name if order.branch else None,
                "coupon": order.coupons.code if order.coupons else None,
                "items": list(order.items.values("menu_item__name", "quantity", "price")),
            }
            return Response(data)

        # Otherwise -> list all
        orders = qs.order_by("-created_at").values(
            "id", "status", "created_at", "branch__name", "coupons__code"
        )
        return Response(list(orders))

    # ✅ 2. CREATE a new order
    def post(self, request, *args, **kwargs):
        data = request.data
        user = request.user

        # Ensure customer_profile exists
        if not hasattr(user, "customer_profile"):
            return Response({"error": "Invalid customer account"}, status=status.HTTP_403_FORBIDDEN)

        branch_id = data.get("branch_id")
        coupon_code = data.get("coupon_code")

        if not branch_id:
            return Response({"error": "branch_id required"}, status=status.HTTP_400_BAD_REQUEST)

        # Validate branch
        branch = Branch.objects.filter(id=branch_id, is_active=True).first()
        if not branch:
            return Response({"error": "Invalid branch"}, status=status.HTTP_404_NOT_FOUND)

        # Optional coupon
        coupon = None
        if coupon_code:
            coupon = Coupons.objects.filter(code=coupon_code).first()
            if not coupon:
                return Response({"error": "Coupon not found"}, status=status.HTTP_400_BAD_REQUEST)
        # skip coupons and discounts for now sha

        # Generate secure delivery phrase
        phrase = generate_passphrase()

        order = Order.objects.create(
            orderer=user.customer_profile,
            branch=branch,
            coupons=coupon,
            delivery_secret_hash=hash_phrase(phrase)
        )

        # TODO: broadcast signal to restaurant sockets
        return Response(
            {
                "order_id": order.id,
                "delivery_passphrase": phrase,
                "message": "Order created successfully"
            },
            status=status.HTTP_201_CREATED
        )

# /orders/<int:order_id>/cancel/
# who is this for the user before payment is made, the payment gatway has been made no pyment is made yet so we need to kill that transaction
class OrderCancelView(APIView):
    authentication_classes = [CustomCustomerAuth]

    def patch(self, request, order_id=None, *args, **kwargs):
        """Customer cancels their own order."""
        if not order_id:
            return Response({"error": "order_id required"}, status=status.HTTP_400_BAD_REQUEST)

        order = Order.objects.filter(id=order_id).first()
        if not order:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

        if order.status not in ["pending", "confirmed"]:
            return Response(
                {"error": "You can only cancel pending or confirmed orders"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.status = "cancelled"
        order.save(update_fields=["status"])
        # TODO: broadcast to restaurant + driver websockets

        return Response({"message": "Order cancelled successfully"}, status=status.HTTP_200_OK)

# custom authentication with select related for this, we need paginification here
# /order/currentactive/
class CurrentActiveOrderView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self, request):
        user = request.user
        if not getattr(user, "customer_profile_id", None):
            return Response({"error": "Invalid customer account"}, status=status.HTTP_403_FORBIDDEN)

        orders = Order.objects.filter(orderer_id=user.customer_profile_id).exclude(status__in=["cancelled", "delivered"])
        # we can add select related here and get all the info we need
        # .values("id", "status", "total_price", "created_at")  # choose useful fields
        # remove some this from it using either selilizers or the values
        return Response({"orders": list(orders.values())})

# finished
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

        if not action or action not in ["accept", "cancel", "made"]:
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
            return self.cancel_order(order)

    def accept_order(self, order: Order): # updates the user and the driver # with consumers or something simular
        if order.status != "pending":
            return Response(
                {"error": "Order already accepted"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = "confirmed"
        order.save(update_fields=["status"])
        total = 1000#order.grand_total
        transaction_data = Transaction.initialize(
            amount=round(total*100),  # amount in kobo (5000 = ₦50.00)
            email='testuser@example.com',
        )
        if not transaction_data['status']: # if false raise error
            return Response(
                {"error": transaction_data['message']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # TODO: trigger driver notification here
        return Response(
            {"message": "Order accepted successfully", "authorization_url": transaction_data['data']['authorization_url']},
            status=status.HTTP_202_ACCEPTED,
        )

    def order_made(self, order: Order): # change this or move to the driver
        if order.status != "preparing":
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

    def cancel_order(self, order: Order): # send request to the drivers and user
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

# /order/driverorder/
class DriverOrderView(GenericAPIView): # selcet related driver_profile, or customer profile
    authentication_classes = [CustomDriverAuth]
    def get_queryset(self):
        user = self.request.user 
        return Order.objects.filter(driver=user.driver_profile)

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
        order_code = request.data.get("order_code")

        if not action or action not in ["accept", "deliver", "reject"]:
            return Response({"error": "Action required"}, status=status.HTTP_400_BAD_REQUEST)
        
        order = self.get_queryset().filter(id=order_id).first()
        if not order:
            return Response(
                {"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND
            )
        
        if action == "accept":
            return self.accept_order(order)
        elif action == "deliver":
            return self.complete_order(order, order_code)
        else:
            # remove notification group btw user, branch, and the driver
            # remove from driver pool too, notified
            return

    def accept_order(self, order: Order): # updates the user and the driver # with consumers or something simular
        if order.status != "ready":
            return Response(
                {"error": "Order not ready for pickup"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = "on_the_way"
        order.save(update_fields=["status"])
        # TODO: trigger user notification here
        return Response(
            {"message": "Order accepted successfully"},
            status=status.HTTP_202_ACCEPTED,
        )
    
    def complete_order(self, order: Order, order_code: str): # updates the user and the driver # with consumers or something simular
        if not order_code:
            return Response(
                {"error": "Order code missing"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if order.status != "on_the_way":
            return Response(
                {"error": "Order already accepted"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        verifed = verify_delivery_phrase(order, order_code)
        if not verifed:
            return Response(
                {"error": "Order failed not verified"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # TODO: trigger user notification here
        # trigger recalculation
        return Response(
            {"message": "Order accepted successfully"},
            status=status.HTTP_202_ACCEPTED,
        )
    # we need to add a timer to check for laps the order should cancle or pay the rest remove the user penelize the stage at fault

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
        branch = None

        if isinstance(user, LinkedStaff):
            branch = user.created_by.branch
        elif isinstance(user, User):
            branch = user.primaryagent.branch
        else:
            return Response(
                {"detail": "user is not a resturant employee"},
                status=status.HTTP_404_NOT_FOUND,
            )

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

if False: # comment
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
    ...
