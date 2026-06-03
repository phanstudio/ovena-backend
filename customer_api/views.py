from common.customer.view import BaseCustomerAPIView
from rest_framework.response import Response
from menu.models import Order
from common.customer.paginations import StandardResultsSetPagination
# from rest_framework.mixins import ListModelMixin
from rest_framework.generics import ListAPIView, RetrieveAPIView
from .serializers import OrderHistorySerializer, OrderRetrieveSerializer, FavoriteCreateSerializer, FavoriteListSerializer
from referrals.models import ProfileReferral
from .models import FavoriteMenuItem
# Create your views here.


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
                .order_by("-created_at"))

class OrderRetrieveView(BaseCustomerAPIView, RetrieveAPIView):
    queryset = Order.objects.all()
    lookup_field = "id"
    serializer_class = OrderRetrieveSerializer
    def get_queryset(self):
        customer = self.get_customer_profile(self.request)
        return (Order.objects.filter(orderer=customer).select_related("branch__business", "branch", "driver")
                .prefetch_related("items"))

class FavoriteCreateView(BaseCustomerAPIView):
    serializer_class = FavoriteCreateSerializer
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        customer = self.get_customer_profile(request)
        _, created = FavoriteMenuItem.objects.get_or_create(
            customer=customer,
            menu_item_id=vd["menu_item_id"]
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
            menu_item_id=vd["menu_item_id"]
        ).delete()

        return Response({"message": "favorite removed"}, 200)

class FavoriteListView(BaseCustomerAPIView, ListAPIView):
    serializer_class = FavoriteListSerializer
    pagination_class = StandardResultsSetPagination
    queryset = FavoriteMenuItem.objects.all()
    def get_queryset(self):
        customer = self.get_customer_profile(self.request)
        return FavoriteMenuItem.objects.filter(customer=customer)

# class UpdateAdressView
# favorite view for menuitem and addons; but endpoint

