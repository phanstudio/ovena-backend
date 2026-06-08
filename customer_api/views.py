from common.customer.view import BaseCustomerAPIView
from rest_framework.response import Response
from menu.models import Order
from common.customer.paginations import StandardResultsSetPagination
# from rest_framework.mixins import ListModelMixin
from rest_framework.generics import ListAPIView, RetrieveAPIView
from .serializers import (
    OrderHistorySerializer, OrderRetrieveSerializer, FavoriteCreateSerializer, 
    FavoriteListSerializer, OrderCalculationGetSerializer
)
# from referrals.models import ProfileReferral
from .models import FavoriteMenuItem
from django.db import transaction
from django.shortcuts import get_object_or_404
from menu.serializers import OrderCreateSerializer
from menu.views import log_created_order
from addresses.utils import make_point, get_cached_distance_km_from_2points
from addresses.serializers import LocationGetSerializer
from accounts.models import Branch
from coupons_discount.models import Coupons
from django.db.models import Q
from menu.serializers.order import calculate_delivery_fee

class GenerateLinkView(BaseCustomerAPIView):
    def get(self, request):
        customer = self.get_customer_profile(request)
        return Response({
                "generated_link": customer.referral_code, 
                "referral_code": customer.referral_code
            }
        )

class OrderHistoryView(BaseCustomerAPIView, ListAPIView):
    queryset = Order.objects.all()
    pagination_class = StandardResultsSetPagination
    serializer_class = OrderHistorySerializer
    def get_queryset(self):
        customer = self.get_customer_profile(self.request)
        return (Order.objects.filter(orderer=customer).select_related("branch__business", "branch", "driver")
                .prefetch_related("items")
                .order_by("-created_at"))

class OrderRetrieveView(BaseCustomerAPIView, RetrieveAPIView):
    queryset = Order.objects.all()
    lookup_field = "id"
    serializer_class = OrderRetrieveSerializer
    def get_queryset(self):
        customer = self.get_customer_profile(self.request)
        return (Order.objects.filter(orderer=customer).select_related("branch__business", "branch", "driver")
                .prefetch_related("items"))

class ReorderView(BaseCustomerAPIView): # location to the body #:attention 
    serializer_class = LocationGetSerializer
    @transaction.atomic
    def post(self, request, order_id):
        customer = self.get_customer_profile(request)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        user_location = make_point(vd["long"], vd["lat"])
        # user_location = customer.default_address.location

        old_order = get_object_or_404(
            Order.objects.prefetch_related(
                "items__variants",
                "items__addons",
            ),
            id=order_id,
            orderer=customer,
        )

        payload = {
            "branch_id": old_order.branch_id,
            "items": [],
        }

        for item in old_order.items.all():
            payload["items"].append({
                "menu_item_id": item.menu_item_id,
                "quantity": item.quantity,
                "variant_option_ids": list(
                    item.variants.values_list("id", flat=True)
                ),
                "addon_ids": list(
                    item.addons.values_list("id", flat=True)
                ),
            })
        
        serializer = OrderCreateSerializer(
            data=payload,
            context={
                "request": request,
                "user": request.user,
                "customer": customer,
                "user_location": user_location
            },
        )

        serializer.is_valid(raise_exception=True)

        order, phrase = serializer.save()

        log_created_order(order, request.user)

        return Response({
            "message": "Order recreated successfully",
            "order_id": order.id,
            "order_number": order.order_number,
            "delivery_passphrase": phrase,
        }, status=201)

class FavoriteCreateView(BaseCustomerAPIView):
    serializer_class = FavoriteCreateSerializer
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        customer = self.get_customer_profile(request)
        _, created = FavoriteMenuItem.objects.get_or_create(
            customer=customer,
            menu_item_id=vd["menu_item_id"],
            branch_id=vd["branch_id"]
        )
        return Response({"message": "success"}, 200)

class FavoriteRemoveView(BaseCustomerAPIView):
    serializer_class = FavoriteCreateSerializer
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        customer = self.get_customer_profile(request)
        FavoriteMenuItem.objects.filter(
            customer=customer,
            menu_item_id=vd["menu_item_id"],
            branch_id=vd["branch_id"]
        ).delete()

        return Response({"message": "favorite removed"}, 200)

class FavoriteListView(BaseCustomerAPIView, ListAPIView):
    serializer_class = FavoriteListSerializer
    pagination_class = StandardResultsSetPagination
    queryset = FavoriteMenuItem.objects.all()
    def get_queryset(self):
        customer = self.get_customer_profile(self.request)
        return FavoriteMenuItem.objects.filter(customer=customer).select_related("menu_item", "branch")

# class UpdateAdressView
# favorite view for menuitem and addons; but endpoint

class OrderCalculationsView(BaseCustomerAPIView):
    serializer_class = OrderCalculationGetSerializer
    @transaction.atomic
    def post(self, request):
        # customer = self.get_customer_profile(request)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        user_location = make_point(vd["long"], vd["lat"])
        
        vd["branch_id"]# or branch long and lat;
        branch = Branch.objects.filter(id=vd["branch_id"], active=True)
        if not branch:
            return Response({"details": "branch id invalid or not active"}, status=401)
        
        delivery_fee = calculate_delivery_fee(
            vd["is_delivery"], get_cached_distance_km_from_2points(user_location, branch.location)
        )
        coupon_code = vd.get("coupon_code", None)
        if coupon_code:
            coupon = Coupons.objects.filter(
                code=coupon_code,
            ).filter(
                Q(
                    is_reward=False,
                    is_active=True,
                )
                |
                Q(
                    is_reward=True,
                    user_wallets__user=request.user,
                    user_wallets__is_used=False,
                )
            ).first()
            if coupon:
                for field in ["is_reward", "created_at"]:
                    coupon.pop(field, None)
            else:
                coupon = "The coupon code has expired"
        else:
            coupon = "No coupon given"

        return Response({
            "message": "Order recreated successfully",
            "delivery_amount": delivery_fee,
            "coupons": coupon
        }, status=201)
