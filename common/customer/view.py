from rest_framework.generics import GenericAPIView
from authflow.permissions import IsCustomer
from authflow.authentication import CustomCustomerAuth
from django.http import Http404
from accounts.models import CustomerProfile


class BaseCustomerAPIView(GenericAPIView):
    authentication_classes = [CustomCustomerAuth]
    permission_classes = [IsCustomer]

    def get_customer_profile(self, request) -> CustomerProfile:
        profile = request.user.customer_profile
        if not profile:
            raise Http404("Customer profile not found")
        return profile
