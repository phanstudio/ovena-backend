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
    Order, Coupons, OrderEvent
)
from .pagifications import StandardResultsSetPagination

from accounts.models import LinkedStaff, User, Rating
from authflow.decorators import subuser_authentication
from authflow.authentication import CustomCustomerAuth, CustomDriverAuth
from authflow.permissions import ScopePermission, ReadScopePermission
from authflow.services import generate_passphrase, hash_phrase, verify_delivery_phrase

from django.shortcuts import get_object_or_404
from django.db.models import Avg, Count, Q
from django.conf import settings
from django.utils import timezone



from .websocket_utils import *
from .tasks import *
import logging
from .payment_services import initialize_paystack_transaction

logger = logging.getLogger(__name__)

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

# who is this for the user before payment is made, the payment gatway has been made no pyment is made yet so we need to kill that transaction
# custom authentication with select related for this, we need paginification here
# finished


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


# first in order split the json into section all the branches and all the categories and etc one by one bulk create each that way the is faster than a for loop-> 
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


class OrderView(APIView):
    authentication_classes = [CustomCustomerAuth]

    def get_queryset(self, request):
        """Return only the logged-in user's orders."""
        user = request.user
        if not hasattr(user, "customer_profile"):
            return Order.objects.none()
        return Order.objects.filter(orderer=user.customer_profile).select_related("branch", "coupons")

    def get(self, request, order_id=None, *args, **kwargs):
        qs = self.get_queryset(request)

        if order_id:
            order = get_object_or_404(qs, id=order_id)
            data = {
                "id": order.id,
                "status": order.status,
                "created_at": order.created_at,
                "branch": order.branch.name if order.branch else None,
                "coupon": order.coupons.code if order.coupons else None,
                "items": list(order.items.values("menu_item__name", "quantity", "price")),
                "websocket_url": f"ws://localhost:8000/ws/orders/{order.id}/",  # Update domain
            }
            return Response(data)

        orders = qs.order_by("-created_at").values(
            "id", "status", "created_at", "branch__name", "coupons__code"
        )
        return Response(list(orders))

    def post(self, request, *args, **kwargs):
        """CREATE a new order with WebSocket broadcast"""
        data = request.data
        user = request.user

        if not hasattr(user, "customer_profile"):
            return Response({"error": "Invalid customer account"}, status=status.HTTP_403_FORBIDDEN)

        branch_id = data.get("branch_id")
        coupon_code = data.get("coupon_code")

        if not branch_id:
            return Response({"error": "branch_id required"}, status=status.HTTP_400_BAD_REQUEST)

        branch = Branch.objects.filter(id=branch_id, is_active=True).first()
        if not branch:
            return Response({"error": "Invalid branch"}, status=status.HTTP_404_NOT_FOUND)

        # Check if branch is accepting orders
        if not branch.is_accepting_orders:
            return Response(
                {"error": "This restaurant is not accepting orders right now"},
                status=status.HTTP_400_BAD_REQUEST
            )

        coupon = None
        if coupon_code:
            coupon = Coupons.objects.filter(code=coupon_code).first()
            if not coupon:
                return Response({"error": "Coupon not found"}, status=status.HTTP_400_BAD_REQUEST)

        # Generate secure delivery phrase
        phrase = generate_passphrase()

        # Create order
        order = Order.objects.create(
            orderer=user.customer_profile,
            branch=branch,
            coupons=coupon,
            delivery_secret_hash=hash_phrase(phrase),
            status='pending'
        )

        # Log event
        OrderEvent.objects.create(
            order=order,
            event_type='created',
            actor_type='customer',
            actor_id=user.customer_profile.id,
            new_status='pending',
            metadata={'items_count': data.get('items_count', 0)}
        )

        # 🔥 Broadcast to branch via WebSocket
        notify_order_created(order)

        # 🔥 Start branch confirmation timeout
        check_branch_confirmation_timeout.apply_async(
            args=[order.id],
            countdown=settings.BRANCH_CONFIRMATION_TIMEOUT
        )

        logger.info(f"Order {order.id} created and broadcasted to branch {branch_id}")

        return Response(
            {
                "order_id": order.id,
                "order_number": order.order_number,
                "delivery_passphrase": phrase,
                "websocket_url": f"ws://localhost:8000/ws/orders/{order.id}/",
                "message": "Order created successfully. Waiting for restaurant confirmation."
            },
            status=status.HTTP_201_CREATED
        )


class OrderCancelView(APIView):
    authentication_classes = [CustomCustomerAuth]

    def patch(self, request, order_id=None, *args, **kwargs):
        """Customer cancels their own order"""
        if not order_id:
            return Response({"error": "order_id required"}, status=status.HTTP_400_BAD_REQUEST)

        order = Order.objects.filter(id=order_id).first()
        if not order:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

        # Can only cancel before driver picks up
        if order.status not in ["pending", "confirmed", "payment_pending"]:
            return Response(
                {"error": "Cannot cancel order at this stage"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = order.status
        order.status = "cancelled"
        order.save(update_fields=["status", "last_modified_at"])

        # Log event
        OrderEvent.objects.create(
            order=order,
            event_type='cancelled',
            actor_type='customer',
            actor_id=request.user.customer_profile.id,
            old_status=old_status,
            new_status='cancelled',
            metadata={'reason': 'customer_cancelled'}
        )

        # 🔥 Broadcast cancellation to all parties
        notify_order_cancelled(
            order,
            reason="Cancelled by customer",
            cancelled_by="customer"
        )

        logger.info(f"Order {order.id} cancelled by customer")

        return Response({"message": "Order cancelled successfully"}, status=status.HTTP_200_OK)


class CurrentActiveOrderView(APIView):
    permission_classes=[IsAuthenticated]
    
    def get(self, request):
        user = request.user
        if not getattr(user, "customer_profile_id", None):
            return Response({"error": "Invalid customer account"}, status=status.HTTP_403_FORBIDDEN)

        orders = Order.objects.filter(
            orderer_id=user.customer_profile_id
        ).exclude(
            status__in=["cancelled", "delivered"]
        ).select_related('branch', 'driver__user')

        order_data = []
        for order in orders:
            order_data.append({
                'id': order.id,
                'order_number': order.order_number,
                'status': order.status,
                'total_price': float(order.grand_total),
                'created_at': order.created_at.isoformat(),
                'branch_name': order.branch.name,
                'driver_name': order.driver.user.get_full_name() if order.driver else None,
                'websocket_url': f"ws://localhost:8000/ws/orders/{order.id}/",
            })

        return Response({"orders": order_data})

@subuser_authentication
class ResturantOrderView(GenericAPIView):
    permission_classes=[ScopePermission, ReadScopePermission]
    pagination_class=StandardResultsSetPagination
    required_scopes = ["order:accept", "order:cancle"]

    def get_queryset(self):
        user = self.request.user
        if isinstance(user, LinkedStaff):
            return Order.objects.filter(branch=user.created_by.branch)
        if isinstance(user, User):
            return Order.objects.filter(branch=user.primaryagent.branch)
        return Order.objects.none()

    def get(self, request, *args, **kwargs):
        qs = self.get_queryset().values(
            "id", "status", "created_at",
            "items__id", "items__menu_item_id", "items__quantity", "items__price"
        )
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(list(page))

    def post(self, request):
        action = request.data.get("action")
        order_id = request.data.get("order_id")

        print(action, order_id)

        if not action or action not in ["accept", "cancel", "made"]:
            return Response({"error": "Action required"}, status=status.HTTP_400_BAD_REQUEST)
        
        order = self.get_queryset().filter(id=order_id).first()
        if not order:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if action == "accept":
            return self.accept_order(order)
        elif action == "made":
            return self.order_made(order)
        else:
            return self.cancel_order(order)

    def accept_order(self, order: Order):
        """Branch accepts order and initiates payment"""
        if order.status != "pending":
            return Response(
                {"error": "Order already processed"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        order.status = "confirmed"
        order.confirmed_at = timezone.now()
        order.save(update_fields=["status", "confirmed_at", "last_modified_at"])

        # Log event
        OrderEvent.objects.create(
            order=order,
            event_type='confirmed',
            actor_type='branch',
            actor_id=order.branch_id,
            old_status='pending',
            new_status='confirmed'
        )

        

        # Initialize payment
        total = 100#order.grand_total  # Use actual total
        # transaction_data = Transaction.initialize(
        #     amount=round(total * 100),  # Convert to kobo
        #     email=self.check_email_with_default(order.orderer.user.email),
        # )
        transaction_data = initialize_paystack_transaction(total, order.orderer.user.email)

        

        if not transaction_data['status']:
            return Response(
                {"error": transaction_data['message']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Save payment reference
        order.payment_reference = transaction_data['data']['reference']
        order.payment_initialized_at = timezone.now()
        order.status = 'payment_pending'
        order.save(update_fields=['payment_reference', 'payment_initialized_at', 'status'])

        payment_url = transaction_data['data']['authorization_url']

        # 🔥 Broadcast to customer with payment URL
        notify_order_confirmed(order, payment_url)

        # 🔥 Start payment timeout
        check_payment_timeout.apply_async(
            args=[order.id],
            countdown=settings.PAYMENT_TIMEOUT
        )

        print(total, transaction_data)

        logger.info(f"Order {order.id} confirmed by branch, payment initiated")

        return Response(
            {
                "message": "Order accepted successfully",
                "authorization_url": payment_url,
                "payment_reference": order.payment_reference
            },
            status=status.HTTP_202_ACCEPTED,
        )

    def order_made(self, order: Order):
        """Mark order as ready and find driver"""
        if order.status != "preparing":
            return Response(
                {"error": "Order must be in preparing status"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        order.status = "ready"
        order.save(update_fields=["status", "last_modified_at"])

        # Log event
        OrderEvent.objects.create(
            order=order,
            event_type='ready',
            actor_type='branch',
            actor_id=order.branch_id,
            old_status='preparing',
            new_status='ready'
        )

        # 🔥 Notify customer and start driver search
        notify_order_ready(order)

        # 🔥 Find and assign driver (async task)
        find_and_assign_driver.delay(order.id)

        logger.info(f"Order {order.id} marked as ready, finding driver")

        return Response(
            {"message": "Order marked as ready. Finding a driver..."},
            status=status.HTTP_200_OK,
        )

    def cancel_order(self, order: Order):
        """Branch cancels order"""
        if order.status in ["delivered", "on_the_way", "picked_up"]:
            return Response(
                {"error": "Cannot cancel at this stage"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        old_status = order.status
        order.status = "cancelled"
        order.save(update_fields=["status", "last_modified_at"])

        # Log event
        OrderEvent.objects.create(
            order=order,
            event_type='cancelled',
            actor_type='branch',
            actor_id=order.branch_id,
            old_status=old_status,
            new_status='cancelled',
            metadata={'reason': 'branch_cancelled'}
        )

        # 🔥 Notify all parties
        notify_order_cancelled(
            order,
            reason="Restaurant cancelled the order",
            cancelled_by="branch"
        )

        logger.info(f"Order {order.id} cancelled by branch")

        return Response(
            {"message": "Order cancelled successfully"},
            status=status.HTTP_200_OK,
        )

class DriverOrderView(GenericAPIView):
    authentication_classes = [CustomDriverAuth]
    
    def get_queryset(self):
        user = self.request.user 
        return Order.objects.filter(driver=user.driver_profile)

    def get(self, request, *args, **kwargs):
        qs = self.get_queryset().select_related('branch', 'orderer__user').values(
            "id", "order_number", "status", "created_at",
            "branch__name", "branch__location",
            "items__id", "items__menu_item_id", "items__quantity", "items__price"
        )
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(list(page))

    def post(self, request):
        action = request.data.get("action")
        order_id = request.data.get("order_id")
        order_code = request.data.get("order_code")

        if not action or action not in ["accept", "deliver", "reject"]:
            return Response({"error": "Action required"}, status=status.HTTP_400_BAD_REQUEST)
        
        order = self.get_queryset().filter(id=order_id).first()
        if not order:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if action == "accept":
            return self.accept_order(order)
        elif action == "deliver":
            return self.complete_order(order, order_code)
        elif action == "reject":
            return self.reject_order(order)

    def accept_order(self, order: Order):
        """Driver accepts order and heads to restaurant"""
        if order.status != "driver_assigned":
            return Response(
                {"error": "Order not available for acceptance"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        order.status = "picked_up"  # Or "on_the_way" to restaurant
        order.picked_up_at = timezone.now()
        order.save(update_fields=["status", "picked_up_at", "last_modified_at"])

        # Log event
        OrderEvent.objects.create(
            order=order,
            event_type='picked_up',
            actor_type='driver',
            actor_id=order.driver_id,
            old_status='driver_assigned',
            new_status='picked_up'
        )

        # 🔥 Notify customer and branch
        notify_order_picked_up(order)

        logger.info(f"Order {order.id} accepted by driver {order.driver_id}")

        return Response(
            {"message": "Order accepted. Head to the restaurant!"},
            status=status.HTTP_202_ACCEPTED,
        )
    
    def complete_order(self, order: Order, order_code: str):
        """Driver delivers order with verification code"""
        if not order_code:
            return Response(
                {"error": "Order code missing"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        if order.status not in ["picked_up", "on_the_way"]:
            return Response(
                {"error": "Order not ready for delivery"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Verify delivery code
        verified = verify_delivery_phrase(order, order_code)
        if not verified:
            return Response(
                {"error": "Invalid delivery code"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        order.status = "delivered"
        order.delivered_at = timezone.now()
        order.delivery_verified = True
        order.delivery_verified_at = timezone.now()
        order.save(update_fields=[
            "status", "delivered_at", "delivery_verified",
            "delivery_verified_at", "last_modified_at"
        ])

        # Update driver availability
        driver = order.driver
        driver.is_available = True
        driver.current_order = None
        driver.total_deliveries += 1
        driver.save(update_fields=['is_available', 'current_order', 'total_deliveries'])

        # Log event
        OrderEvent.objects.create(
            order=order,
            event_type='delivered',
            actor_type='driver',
            actor_id=order.driver_id,
            old_status=order.status,
            new_status='delivered'
        )

        # 🔥 Notify all parties of successful delivery
        notify_order_delivered(order)

        # TODO: Process payments to branch and driver

        logger.info(f"Order {order.id} delivered successfully by driver {order.driver_id}")

        return Response(
            {"message": "Order delivered successfully!"},
            status=status.HTTP_200_OK,
        )
    
    def reject_order(self, order: Order):
        """Driver rejects order assignment"""
        if order.status != "driver_assigned":
            return Response(
                {"error": "Cannot reject at this stage"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        driver_id = order.driver_id
        
        # Reset order status
        order.driver = None
        order.status = "ready"
        order.save(update_fields=["driver", "status", "last_modified_at"])

        # Update driver
        driver = DriverProfile.objects.get(id=driver_id)
        driver.is_available = True
        driver.current_order = None
        driver.save(update_fields=['is_available', 'current_order'])

        # Log event
        OrderEvent.objects.create(
            order=order,
            event_type='driver_rejected',
            actor_type='driver',
            actor_id=driver_id,
            metadata={'reason': 'manual_rejection'}
        )

        # 🔥 Find alternative driver
        find_and_assign_driver.delay(order.id, excluded_driver_ids=[driver_id])

        logger.info(f"Driver {driver_id} rejected order {order.id}")

        return Response(
            {"message": "Order rejected. Finding alternative driver..."},
            status=status.HTTP_200_OK
        )
