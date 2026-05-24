from common.customer.view import BaseCustomerAPIView
from rest_framework.response import Response
from menu.models import Order
from common.customer.paginations import StandardResultsSetPagination
# from rest_framework.mixins import ListModelMixin
from rest_framework.generics import ListAPIView, RetrieveAPIView
from .serializers import OrderHistorySerializer, OrderRetrieveSerializer
from referrals.models import ProfileReferral
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
                
