from common.customer.view import BaseCustomerAPIView
from rest_framework.response import Response
from menu.models import Order
from common.customer.paginations import StandardResultsSetPagination
# from rest_framework.mixins import ListModelMixin
from rest_framework.generics import ListAPIView, RetrieveAPIView
from .serializers import (
    OrderHistorySerializer, OrderRetrieveSerializer, FavoriteCreateSerializer, 
    FavoriteListSerializer, OrderCalculationGetSerializer, StoreDetailsSerializer,
    AccountCreateSerializer, AccountDetailSerializer, AccountChangeConfirmSerializer, AccountChangeRequestSerializer
)
# from referrals.models import ProfileReferral
from django.conf import settings
from .models import FavoriteMenuItem
from django.db import transaction
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from menu.serializers import OrderCreateSerializer
from menu.views import log_created_order, create_payment
from addresses.utils import make_point, get_cached_distance_km_from_2points
from addresses.serializers import LocationGetSerializer
from accounts.models import Branch
from coupons_discount.models import Coupons
from django.db.models import Q
from menu.serializers.order import calculate_delivery_fee, PLATFORM_FEES_PERCENT
from payments.models import UserAccount
from rest_framework import status
from authflow.services import OTPManager, OTPInvalidError
from common.utils.compression import decode_dict, encode_dict
from accounts.models import User
from payments.payouts.tasks import ensure_paystack_recipient_for_user_accounts

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
        return (Order.objects.filter(orderer=customer).select_related("branch__business", "branch", "driver__user")
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

        with transaction.atomic():
            order, phrase = serializer.save()
            # Initialize payment via Sale (unified payments)
            payment_url = create_payment(order)

        log_created_order(order, request.user, payment_url)

        return Response({
            "message": "Order recreated successfully",
            "order_id": order.id,
            "order_number": order.order_number,
            "delivery_passphrase": phrase,
            "payment_url": payment_url,
            "websocket_url": f"{settings.WEBSOCKET_URL}/ws/orders/{order.id}/",
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
        message = "created" if created else "already created"
        return Response({"message": f"success, {message}"}, 200)


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


class StoreDetailsView(BaseCustomerAPIView, RetrieveAPIView):
    queryset = Branch.objects.all()
    lookup_field = "id"
    serializer_class = StoreDetailsSerializer
    def get_queryset(self):
        return (Branch.objects.select_related("business", "primary_agent").prefetch_related("operating_hours"))


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
        branch = Branch.objects.filter(id=vd["branch_id"], is_active=True).first()
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
            ).values().first()
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
            "coupons": coupon,
            "service_fee_percent": PLATFORM_FEES_PERCENT,
        }, status=201)


class SendVerifyMixin():
    def send(self, identifier, channel: str = "phone", validator: str= "vaildator"):
        data = encode_dict(self.get_secert_code(validator, identifier))
        code = OTPManager.send_blank(data)
        OTPManager.send_code(channel, identifier, code)
        return code
    
    def verify(self, otp_code: str, unidentified_id:str, validator: str= "vaildator"): # a verify where we return the info
        try:
            identifier = OTPManager.verify(otp_code=otp_code)
            vaild_data:str = decode_dict(identifier)
            if vaild_data != self.get_secert_code(validator, unidentified_id):
                return None, Response(
                    {"error": "The otp code was not generated by us or mismathc in the identifiers"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        except OTPInvalidError as e:
            return None, Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return unidentified_id, None

    def get_secert_code(self, validator, identifier):
        return f"{validator};{identifier}"


class UserAccountCreateView(BaseCustomerAPIView):
    """
    """
    serializer_class = AccountCreateSerializer
    def post(self, request):
        user = request.user

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment_data = serializer.validated_data

        if hasattr(user, "payment_account"):
            return Response(
                {"detail": "Payment account already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            account = UserAccount(
                user=user,
                bank_name=payment_data["bank_name"],
                bank_code=payment_data["bank_code"],
                bank_account_number=payment_data["bank_account_number"],
                bank_account_name=payment_data["bank_account_name"],
            )

            account.set_transaction_pin(payment_data["transaction_pin"])
            account.save()
            ensure_paystack_recipient_for_user_accounts.delay(account.pk)
        except IntegrityError:
            return Response(
                {"detail": "Payment account already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Bank Account Saved."}, status=status.HTTP_200_OK)


class UserAccountRetrieveView(RetrieveAPIView):
    serializer_class = AccountDetailSerializer

    def get_object(self):
        return get_object_or_404(
            UserAccount,
            user=self.request.user,
        )


class UserAccountChangeRequestView(BaseCustomerAPIView, SendVerifyMixin):
    """
    """
    serializer_class = AccountChangeRequestSerializer
    def post(self, request):
        user = request.user

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        try:
            account = UserAccount.objects.get(user=user)
            if (
                account.last_bank_change_at
                and account.last_bank_change_at.date() == timezone.now().date()
            ):
                return Response(
                    {"detail": "You can only change your bank account once every day."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            is_vaild = account.check_transaction_pin(vd["transaction_pin"])
            if not is_vaild:
                return Response({"detail": "Incorrect pin"}, status=status.HTTP_400_BAD_REQUEST)
            self.send(user.email, "email", "AccountChange")
            
        except UserAccount.DoesNotExist:
            return Response({"detail": "Account doesn't exist"}, status=status.HTTP_404_NOT_FOUND)


        return Response({"detail": "Verification code sent."}, status=status.HTTP_200_OK)


class UserAccountChangeConfirmView(BaseCustomerAPIView, SendVerifyMixin):
    """
    """
    serializer_class = AccountChangeConfirmSerializer
    def post(self, request):
        user:User = request.user

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment_data = serializer.validated_data

        _, error = self.verify(payment_data["otp_code"], user.email, "AccountChange")
        if error:
            return error

        with transaction.atomic():
            account = UserAccount.objects.select_for_update().get(user=user)

            account.bank_name = payment_data["bank_name"]
            account.bank_code = payment_data["bank_code"]
            account.bank_account_number = payment_data["bank_account_number"]
            account.bank_account_name = payment_data["bank_account_name"]
            account.last_bank_change_at = timezone.now()

            # Important
            account.paystack_recipient_code = ""
            account.save()

        ensure_paystack_recipient_for_user_accounts.delay(account.pk)

        return Response({"detail": "Change complete."}, status=status.HTTP_200_OK)

# class UpdateAdressView
