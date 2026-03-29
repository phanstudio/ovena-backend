from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.generics import GenericAPIView
from menu.models import (
    Order, OrderEvent, OrderItem, DriverProfile
)
from menu.pagifications import StandardResultsSetPagination

from accounts.models import User
from authflow.authentication import CustomCustomerAuth, CustomDriverAuth, CustomBStaffAuth
from authflow.permissions import IsCustomer, IsBusinessStaff, IsDriver
from authflow.services import verify_delivery_phrase

from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone

from menu.websocket_utils import (
    notify_order_cancelled, notify_order_created, notify_order_ready, notify_order_confirmed, 
    notify_order_delivered, notify_order_picked_up
)
from menu.tasks import check_branch_confirmation_timeout, find_and_assign_driver, check_payment_timeout
import logging
from menu.payment_services import initialize_order_sale
from django.db import transaction
from menu.serializers import OrderCreateSerializer
from django.db.models import Prefetch
from referrals.services import convert_referral_once
from payments.services.sale_service import complete_service, assign_driver
from driver_api.services import ledger_credit_for_delivered_order

logger = logging.getLogger(__name__)

class OrderView(APIView):
    authentication_classes = [CustomCustomerAuth]
    permission_classes = [IsCustomer]
    
    def get_list_queryset(self, request):
        user = request.user
        if not hasattr(user, "customer_profile"):
            return Order.objects.none()
        return Order.objects.filter(orderer=user.customer_profile).select_related("branch", "coupons")

    def get_detail_queryset(self, request):
        return self.get_list_queryset(request).prefetch_related(
            Prefetch(
                "items",
                queryset=OrderItem.objects
                    .select_related("menu_item", "menu_item__base_item")
                    .prefetch_related("variants", "addons")
            )
        )

    def get(self, request, order_id=None, *args, **kwargs):
        """
        This function retrieves order details and items information based on the order ID or returns a
        list of orders with specific fields.
        
        :param request: The `get` method you provided is a part of a Django REST framework view. It
        handles GET requests for retrieving order details based on the `order_id` provided in the URL.
        Here's a breakdown of the parameters used in the method:
        :param order_id: The `order_id` parameter in the `get` method is used to retrieve a specific
        order based on its ID. If the `order_id` is provided, the method fetches the order details and
        related items to construct a response for that specific order. If `order_id` is not provided
        :return: The `get` method returns a response containing order details if an `order_id` is
        provided. If no `order_id` is provided, it returns a list of orders with limited details such as
        order id, status, creation date, branch name, and coupon code.
        """

        if order_id:
            qs = self.get_list_queryset(request)
            order = get_object_or_404(qs, id=order_id)
            items_payload = []
            for item in order.items.all():
                snap = item.snapshot or {}

                name = (getattr(item.menu_item, "custom_name", None) or "").strip()
                if not name:
                    # fallback: base_item name
                    if item.menu_item_id and item.menu_item.base_item_id:
                        name = item.menu_item.base_item.name
                if not name:
                    # fallback: snapshot
                    name = snap.get("menu_item", {}).get("name")

                items_payload.append({
                    "name": name,
                    "quantity": item.quantity,
                    "price": str(item.price),
                    "added_total": str(item.added_total),
                    "line_total": str(item.line_total),

                    # OPTIONAL: only include snapshot details if you want
                    # "snapshot": snap,
                })


            data = {
                "id": order.id,
                "status": order.status,
                "created_at": order.created_at,
                "branch": order.branch.name if order.branch else None,
                "coupon": order.coupons.code if order.coupons else None,
                # "items": list(order.items.values("menu_item__name", "quantity", "price")),
                "items": items_payload,
                "websocket_url": f"{settings.WEBSOCKET_URL}/ws/orders/{order.id}/",  # Update domain
            }
            return Response(data)

        qs = self.get_detail_queryset(request)
        orders = qs.order_by("-created_at").values(
            "id", "status", "created_at", "branch__name", "coupons__code"
        )
        return Response(list(orders))

    # the order item part can be handeled with a serilizer and bulk create; also should an order be made with no 
    # items also there is a minimum of 5000 order amount i.e line total before discount per order. 
    # also the variats and addons should be there too.
    def post(self, request, *args, **kwargs):
        user = request.user
        if not hasattr(user, "customer_profile"):
            return Response({"error": "Invalid customer account"}, status=status.HTTP_403_FORBIDDEN)

        serializer = OrderCreateSerializer(
            data=request.data,
            context={"request": request, "user": user},
        )
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            order, phrase = serializer.save()

        # log + websocket + timeout (same as you already do)
        OrderEvent.objects.create(
            order=order,
            event_type="created",
            actor_type="customer",
            actor_id=user.customer_profile.id,
            new_status="pending",
            metadata={"items_count": order.items.count()},
        )

        notify_order_created(order)

        check_branch_confirmation_timeout.apply_async(
            args=[order.id],
            countdown=settings.BRANCH_CONFIRMATION_TIMEOUT
        )

        return Response(
            {
                "order_id": order.id,
                "order_number": order.order_number,
                "delivery_passphrase": phrase,
                "websocket_url": f"{settings.WEBSOCKET_URL}/ws/orders/{order.id}/",
                "message": "Order created successfully. Waiting for restaurant confirmation.",
            },
            status=status.HTTP_201_CREATED,
        )


class OrderCancelView(APIView):
    authentication_classes = [CustomCustomerAuth]

    def patch(self, request, order_id=None, *args, **kwargs):
        """Customer cancels their own order"""
        user = request.user.customer_profile
        if not order_id:
            return Response({"error": "order_id required"}, status=status.HTTP_400_BAD_REQUEST)

        order:Order = Order.objects.filter(id=order_id).first()
        if not order:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if order.orderer_id != user.id:
            return Response({"error": "Invalid customer account"}, status=status.HTTP_403_FORBIDDEN)

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
            actor_id=user.id,
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
                'websocket_url': f"{settings.WEBSOCKET_URL}/ws/orders/{order.id}/",
            })

        return Response({"orders": order_data})

class ResturantOrderView(GenericAPIView):
    authentication_classes=[CustomBStaffAuth]
    permission_classes=[IsBusinessStaff]
    pagination_class=StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
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

        # Initialize payment via Sale (unified payments)
        try:
            sale_result = initialize_order_sale(order)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Save payment reference
        order.payment_reference = sale_result["reference"]
        order.payment_initialized_at = timezone.now()
        order.status = 'payment_pending'
        order.sale_id = sale_result["sale_id"]
        order.save(update_fields=['payment_reference', 'payment_initialized_at', 'status', 'sale'])

        payment_url = sale_result["payment_url"]

        # 🔥 Broadcast to customer with payment URL
        notify_order_confirmed(order, payment_url)

        # 🔥 Start payment timeout
        check_payment_timeout.apply_async(
            args=[order.id],
            countdown=settings.PAYMENT_TIMEOUT
        )

        logger.info("Order %s sale initialized via payments service", order.id)

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
    permission_classes = [IsDriver]
    
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
        user = self.request.user

        if not action or action not in ["accept", "deliver", "reject"]:
            return Response({"error": "Action required"}, status=status.HTTP_400_BAD_REQUEST)
        
        order = self.get_queryset().filter(id=order_id).first()
        if not order:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if action == "accept":
            return self.accept_order(order, user)
        elif action == "deliver":
            return self.complete_order(order, order_code)
        elif action == "reject":
            return self.reject_order(order)

    def accept_order(self, order: Order, user: User):
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
        assign_driver(order, user.id)

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

        # Conversion criteria:
        # - referee customer converts on first delivered order
        # - referee driver converts on first completed delivery
        convert_referral_once(referee_profile=order.orderer)
        if driver:
            convert_referral_once(referee_profile=driver)

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
        # trigger first split and crediting
        sale_result = complete_service(order.sale.id)
        ledger_credit_for_delivered_order(order)
        logger.info(f"sale info: {sale_result}")

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
