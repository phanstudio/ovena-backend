from admin_api.models import AppAdmin
from accounts.models import User, DriverProfile
from admin_api.serializers import (
    LoginResponseSerializer, AppAdminLoginSerializer,
    UserSerializer, AppAdminProfileSerializer, UpdateAppAdminSerializer
)
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema # type: ignore
from authflow.services import issue_jwt_for_user
from rest_framework.permissions import AllowAny
from rest_framework.generics import GenericAPIView, RetrieveAPIView, ListAPIView
from authflow.permissions import IsAppAdmin
from authflow.authentication import CustomAppAdminAuth
from rest_framework.exceptions import NotFound
from referrals.models import ReferralPayout
from referrals.serializers import ReferralPayoutSerializer
from referrals.services import verify_snapshot_integrity
from django.db.models import Sum


# employee management i.e drivers and restaurants, users(i.e customers)
# see user need to referral payment and when
# see requests to withdraw
# notifications
# withdrawals system
# current number of users
# dashboard to see stats;

## pending
# check new driver and restaurants;
# send codes to create;

# admin login ✅
# the profile for the admins ✅
# auth and permissions ✅
# user update admin ✅
# referrals system?? ✅
# coupon creation ✅
# support tickets ✅

class BaseAppAdminAPIView(GenericAPIView):
    authentication_classes = [CustomAppAdminAuth]
    permission_classes = [IsAppAdmin]
    def get_app_admin(self, request) -> AppAdmin:
        try:
            return request.user.app_admin
        except AppAdmin.DoesNotExist:
            raise NotFound("Driver profile not found")
    
    # 🔥 NEW: safe serializer validator helper
    def validate_serializer(self, data=None, *, context=None):
        serializer_class = self.get_serializer_class()

        if not serializer_class:
            raise AssertionError("No serializer_class defined for this view")

        serializer = serializer_class(
            data=data or self.request.data,
            context=context or self.get_serializer_context()
        )

        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

@extend_schema(
    responses={200: LoginResponseSerializer},auth=[]
)
class AdminLoginView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = AppAdminLoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        user = User.objects.filter(phone_number=vd["phone_number"]).first()
        if not user:
            return Response(
                {"error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        app_admin: AppAdmin = getattr(user, "app_admiin", None)
        if not app_admin:
            return Response(
                {"error": "Not a business admin account"},
                status=status.HTTP_403_FORBIDDEN
            )
        if not user or not user.check_password(vd["password"]):
            return Response(
                {"error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        token = issue_jwt_for_user(user)
        return Response({
            "message": "Logged in successfully",
            "access": token["access"],
            "refresh": token["refresh"],
        })

class UserProfileView(BaseAppAdminAPIView):
    def get(self, request):
        user = request.user
        
        return Response({
            "user": UserSerializer(user).data,
            "profile": AppAdminProfileSerializer(user.app_admin).data,
        })

# class DriverDashboardView(BaseDriverAPIView):
#     @extend_schema(responses=DriverDashboardSerializer)
#     def get(self, request):
#         driver = self.get_driver(request)
#         wallet = sync_wallet_from_ledger(driver)
#         active_order = None
#         if driver.current_order_id:
#             order = driver.current_order
#             active_order = {
#                 "id": order.id,
#                 "order_number": order.order_number,
#                 "status": order.status,
#                 "created_at": order.created_at,
#             }
#         payload = {
#             "profile": {
#                 "id": driver.id,
#                 "first_name": driver.first_name,
#                 "last_name": driver.last_name,
#                 "rating": driver.avg_rating,
#                 "total_deliveries": driver.total_deliveries,
#                 "is_online": driver.is_online,
#                 "is_available": driver.is_available,
#                 "referral_code": driver.referral_code,
#             },
#             "wallet": {
#                 "current_balance": wallet.current_balance,
#                 "available_balance": wallet.available_balance,
#                 "pending_balance": wallet.pending_balance,
#             },
#             "active_order": active_order,
#             "unread_notifications": get_unread_count(request.user),
#             "open_tickets": get_driver_open_ticket_count(driver),
#         }
#         return Response({"detail": "Driver dashboard loaded", "data": payload})

# app approve drivers and approve resturant owner proposals??
# class UserProfileView(GenericAPIView):
#     authentication_classes = [CustomAppAdminAuth]
#     permission_classes = [IsAppAdmin]

#     def get(self, request):
#         user = request.user
#         DriverProfile.objects.filter()
#         return Response({})
    
# class UserProfileView(GenericAPIView):
#     authentication_classes = [CustomAppAdminAuth]
#     permission_classes = [IsAppAdmin]

#     def get(self, request):
#         user = request.user
#         DriverProfile.objects.filter()
#         return Response({})

class UpdateAppAdmin(BaseAppAdminAPIView):

    def patch(self, request):
        serializer = UpdateAppAdminSerializer(
            instance=request.user.app_admin,
            data=request.data,
            context={"user": request.user},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Profile updated successfully"},
            status=status.HTTP_200_OK,
        )

class AdminReferralPayoutListView(BaseAppAdminAPIView, ListAPIView):
    serializer_class = ReferralPayoutSerializer

    def get_queryset(self):
        qs = (
            ReferralPayout.objects
            .select_related("user")
            .order_by("-created_at")
        )

        user_id = self.request.query_params.get("user_id")
        if user_id:
            qs = qs.filter(user_id=user_id)

        return qs

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()

        total_units = qs.aggregate(
            total=Sum("units_paid")
        )["total"] or 0

        total_payouts = qs.count()

        serializer = self.get_serializer(qs, many=True)

        return Response({
            "count": total_payouts,
            "total_units_paid": total_units,
            "results": serializer.data,
        })

class AdminReferralPayoutDetailView(BaseAppAdminAPIView, RetrieveAPIView):
    queryset = ReferralPayout.objects.all()
    serializer_class = ReferralPayoutSerializer

    def retrieve(self, request, *args, **kwargs):
        payout = self.get_object()

        return Response({
            "id": payout.id,
            "user_id": payout.user_id,
            "units_paid": payout.units_paid,
            "referrals_used": payout.referrals_used,
            "created_at": payout.created_at,

            # 🔥 include snapshot here
            "referrals": payout.referral_snapshot,
            "is_valid": verify_snapshot_integrity(payout)
        })
