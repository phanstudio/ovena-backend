from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from accounts.serializers import (
    CustomerProfileSerializer, DriverProfileSerializer,
    CreateCustomerSerializer, UpdateCustomerSerializer,
    BuisnessAdminProfileSerializer, PrimaryAgentProfileSerializer
)
from accounts.models import(
    User, Branch, PrimaryAgent, 
    BusinessAdmin, BusinessPayoutAccount, BranchOperatingHours
)
from django.db import transaction, IntegrityError
from authflow.services import (
    issue_jwt_for_user, verify, OTPInvalidError, OTPManager
)
from django.contrib.gis.geos import Point
from authflow.authentication import CustomCustomerAuth, CustomBAdminAuth
from authflow.permissions import IsBusinessAdmin
from accounts.services.roles import get_user_roles
from accounts.services.profiles import PROFILE_BUSINESS_ADMIN, get_profile
from drf_spectacular.utils import extend_schema, inline_serializer # type: ignore
from rest_framework import serializers as s
from accounts.serializers import InS, OpS


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        requested_type = request.query_params.get("profile_type")
        user_roles = sorted(get_user_roles(user))

        active_profile_type = requested_type
        if requested_type == "customer":
            profile = getattr(user, "customer_profile", None)
            if not profile:
                return Response({"detail": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)
            serializer = CustomerProfileSerializer(profile)
        elif requested_type == "driver":
            profile = getattr(user, "driver_profile", None)
            if not profile:
                return Response({"detail": "Driver profile not found."}, status=status.HTTP_404_NOT_FOUND)
            serializer = DriverProfileSerializer(profile)
        elif requested_type == "businessadmin":
            profile = getattr(user, "business_admin", None)
            if not profile:
                return Response({"detail": "Business Admin profile not found."}, status=status.HTTP_404_NOT_FOUND)
            serializer = BuisnessAdminProfileSerializer(profile)
        elif requested_type in ("businessstaff", "buisnessstaff"):
            profile = getattr(user, "primaryagent", None)
            if not profile:
                return Response({"detail": "Primary Agent profile not found."}, status=status.HTTP_404_NOT_FOUND)
            serializer = PrimaryAgentProfileSerializer(profile)
        elif hasattr(user, "customer_profile"):
            serializer = CustomerProfileSerializer(user.customer_profile)
            active_profile_type = "customer"
        elif hasattr(user, "driver_profile"):
            serializer = DriverProfileSerializer(user.driver_profile)
            active_profile_type = "driver"
        elif hasattr(user, "business_admin"):
            serializer = BuisnessAdminProfileSerializer(user.business_admin)
            active_profile_type = "businessadmin"
        elif getattr(user, "primaryagent", None):
            serializer = PrimaryAgentProfileSerializer(user.primaryagent)
            active_profile_type = "businessstaff"
        else:
            return Response({"detail": "No profile found for this user."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "user": {
                "id": user.id,
                "email": user.email,
                "phone_number": user.phone_number,
                "name": user.name,
                "roles": user_roles,
                "active_profile_type": active_profile_type,
            },
            "profile": serializer.data,
        })

class Delete2AccountView(APIView):
    def delete(self, request):
        user_id = request.data.get("user_id")
        User.objects.filter(id=user_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class DeleteAccountView(APIView): # will change to a soft delete
    permission_classes = [IsAuthenticated]
    def delete(self, request):
        user = request.user
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT) # remove the delete later

class UpdateBranch(APIView):
    def patch(self, request, branch_id):
        lat = request.data.get("lat")
        long = request.data.get("long")
        phone_number = request.data.get("phone_number")
        branch_name = request.data.get("branch_name")

        update_data = {}

        # ✅ Update location ONLY if both lat & long are provided
        if lat is not None and long is not None:
            update_data["location"] = Point(float(long), float(lat), srid=4326)

        # ✅ Update phone number only if provided
        if phone_number is not None:
            update_data["phone_number"] = phone_number

        # ✅ Update branch name only if provided
        if branch_name is not None:
            update_data["name"] = branch_name

        if not update_data:
            return Response(
                {"detail": "No fields provided to update"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated = Branch.objects.filter(id=branch_id).update(**update_data)

        if not updated:
            return Response(
                {"detail": "Branch not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {"detail": "Branch updated successfully"},
            status=status.HTTP_200_OK,
        )

@extend_schema(
    responses={200: inline_serializer("LinkRequestCreateResponse", fields={"otp": s.CharField()})},
)
class LinkRequestCreateView(GenericAPIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]
    def post(self, request):
        user = request.user
        otp = OTPManager.send_blank(user.phone_number) # or id since it can be auto gen
        return Response({"otp": otp})

# might add password
# check if the user is not revocked
@extend_schema(
    responses=OpS.RegisterBAdminResponseSerializer,
    auth=[],
)
class LinkApproveView(GenericAPIView):
    serializer_class = InS.LinkApproveSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        device_id = vd["device_id"]
        
        try:
            identifier = OTPManager.verify(otp_code=vd["otp"])
        except OTPInvalidError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # # Fetch PrimaryAgent in one query
        # business_admin = (
        #     BusinessAdmin.objects
        #     .select_related("user", "branch")
        #     .filter(user__phone_number=identifier)
        #     .first()
        # )

        # # validate branch belongs to admin
        # branch = Branch.objects.filter(
        #     id=vd["branch_id"],
        #     business=business_admin.business
        # ).first()

        branch = (
            Branch.objects
            .select_related("business__admin__user")
            .filter(
                id=vd["branch_id"],
                business__admin__user__phone_number=identifier
            )
            .first()
        )

        if not branch:
            return Response(
                {"detail": "Invalid branch or not authorized"},
                status=403
            )

        business_admin = branch.business.admin

        if not branch:
            return Response(
                {"detail": "Invalid branch"},
                status=403
            )

        # ensure only one primary agent per branch
        if hasattr(branch, "primary_agent"):
            return Response(
                {"detail": "Branch already has a primary agent"},
                status=400
            )

        # if not business_admin:
        #     return Response(
        #         {"detail": "User not a manager."},
        #         status=status.HTTP_404_NOT_FOUND
        #     )
        try:
            with transaction.atomic():
                user, _ = User.objects.get_or_create(
                    phone_number=vd["phone_number"],
                    defaults={"name": vd["username"] or device_id}
                )

                sub_user = PrimaryAgent.objects.create(
                    created_by=business_admin,
                    device_name=device_id,
                    # branch_id=vd["branch_id"],
                    branch=branch,
                    user=user
                )

        except IntegrityError as _:
            return Response(
                {"error": "A device_id is already linked"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        
        token = issue_jwt_for_user(user)
        response = OpS.RegisterBAdminResponseSerializer({
            "message": "Account registered successfully",
            "refresh": token["refresh"],
            "access": token["access"],
            "user": {"id": sub_user.id, "name": sub_user.device_name},
        })
        return Response(
            response.data,
            status=status.HTTP_201_CREATED,
        )

# add transfer of ownershp later
class RegisterCustomer(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateCustomerSerializer(
            data=request.data,
            context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Customer registered successfully"},
            status=status.HTTP_201_CREATED
        )

class UpdateCustomer(APIView):
    authentication_classes = [CustomCustomerAuth]
    permission_classes = [IsAuthenticated]

    def put(self, request):
        serializer = UpdateCustomerSerializer(
            instance=request.user.customer_profile,
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


# read 
class BranchOperatingHoursView(APIView):
    """
    GET/PUT operating hours for a specific branch.
    Useful for editing hours after onboarding.
    """
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]
    def get(self, request, branch_id):
        user = request.user
        try:
            admin = user.business_admin
        except BusinessAdmin.DoesNotExist:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        branch = Branch.objects.filter(id=branch_id, restaurant=admin.business).first()
        if not branch:
            return Response({"detail": "Branch not found."}, status=status.HTTP_404_NOT_FOUND)

        hours = BranchOperatingHours.objects.filter(branch=branch).order_by("day")
        serializer = InS.BranchOperatingHoursSerializer(hours, many=True)
        return Response(serializer.data)

    def put(self, request, branch_id):
        user = request.user
        try:
            admin = user.business_admin
        except BusinessAdmin.DoesNotExist:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        branch = Branch.objects.filter(id=branch_id, restaurant=admin.business).first()
        if not branch:
            return Response({"detail": "Branch not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = InS.BranchOperatingHoursSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            BranchOperatingHours.objects.filter(branch=branch).delete()
            BranchOperatingHours.objects.bulk_create([
                BranchOperatingHours(branch=branch, **h)
                for h in serializer.validated_data
            ])

        return Response({"detail": "Operating hours updated."})

class RestaurantPaymentView(APIView):
    """
    GET/PUT payment details for the restaurant.
    """
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def get(self, request):
        user = request.user
        try:
            admin = user.business_admin
        except BusinessAdmin.DoesNotExist:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        try:
            payment = admin.business.payout
        except BusinessPayoutAccount.DoesNotExist:
            return Response({"detail": "No payment info set."}, status=status.HTTP_404_NOT_FOUND)

        serializer = InS.RestaurantPaymentSerializer(payment)
        return Response(serializer.data)

    def put(self, request):
        user = request.user
        try:
            admin = user.business_admin
        except BusinessAdmin.DoesNotExist:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        serializer = InS.RestaurantPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        BusinessPayoutAccount.objects.update_or_create(
            business=admin.business,
            defaults={
                "bank_name": vd["bank"],
                "bank_code": vd.get("bank_code", ""),
                "account_number": vd["account_number"],
                "account_name": vd["account_name"],
                "bvn": vd["bvn"],
            },
        )
        return Response({"detail": "Payment info updated."})


# Login views
@extend_schema(
    responses={
        200: inline_serializer("DriverLoginResponse", fields={
            "message": s.CharField(),
            "access": s.CharField(),
            "refresh": s.CharField(),
        })
    },
    auth=[]
)
class DriverLoginView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = InS.DriverLoginSerializer

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
        
        driver_profile = getattr(user, "driver_profile", None)
        if not driver_profile:
            return Response(
                {"error": "Driver profile missing"},
                status=status.HTTP_403_FORBIDDEN
            )

        # if not driver_profile.is_approved:
        #     return Response(
        #         {"error": "Account pending approval"},
        #         status=status.HTTP_403_FORBIDDEN
        #     )
        
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

@extend_schema(
    responses={
        200: inline_serializer("AdminLoginResponse", fields={
            "message": s.CharField(),
            "access": s.CharField(),
            "refresh": s.CharField(),
        })
    },
    auth=[]
)
class AdminLoginView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = InS.AdminLoginSerializer

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
        buisness_admin_role = get_profile(user, PROFILE_BUSINESS_ADMIN)
        if not buisness_admin_role:
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

@extend_schema(
    responses={
        200: inline_serializer("AdminChangePasswordResponse", fields={
            "message": s.CharField(),
        })
    },
)
class AdminChangePasswordView(GenericAPIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]
    serializer_class = InS.AdminChangePasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        user:User = request.user
        if user.check_password(vd["password"]):
            return Response(
                {"error": "Invalid password"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        user.set_password(vd["new_password"])
        user.save(update_fields=["password"])
        return Response({ "message": "Password Changed" })

# @extend_schema(
#     responses={
#         200: inline_serializer("AdminLoginResponse", fields={
#             "message": s.CharField(),
#             "access": s.CharField(),
#             "refresh": s.CharField(),
#         })
#     },
# )
# class AdminTransactionpinView(GenericAPIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]
    serializer_class = InS.AdminChangePasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        user:User = request.user
        if user.check_password(vd["password"]):
            return Response(
                {"error": "Invalid password"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        user.set_password(vd["new_password"])
        user.save(update_fields=["password"])
        return Response({
            "message": "Password Changed",
        })


@extend_schema(
    responses={200: inline_serializer("PasswordResetResponse", fields={
        "message": s.CharField(),
    })},
    auth=[]
)
class PasswordResetView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = InS.PasswordResetSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        try:
            identifier = verify(vd["otp_code"], vd["phone_number"])
        except OTPInvalidError as e:
            return Response({"error": str(e)}, status=400)

        user = User.objects.filter(phone_number=identifier).first()
        if not user:
            return Response({"error": "User not found"}, status=404)

        user.set_password(vd["new_password"])
        user.save(update_fields=["password"])

        # force re-login on all devices
        # if you store a token version on the user model you can invalidate all JWTs
        # simplest approach: tell frontend to discard tokens and re-login

        return Response({"message": "Password updated successfully"})

class StaffLoginView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = InS.LinkStaffLoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        device_id = vd["device_id"] # migth add branch_id
        buisness_staff = PrimaryAgent.objects.filter(device_name=device_id).select_related("user").first()
        user = buisness_staff.user
        
        if not buisness_staff:
            return Response(
                {"error": "Account doesn't exist"},
                status=status.HTTP_403_FORBIDDEN
            )

        if not buisness_staff.revoked:
            return Response(
                {"error": "Account revoked"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # if not user or not user.check_password(vd["password"]):
        #     return Response(
        #         {"error": "Invalid credentials"},
        #         status=status.HTTP_401_UNAUTHORIZED
        #     )

        token = issue_jwt_for_user(user)
        return Response({
            "message": "Logged in successfully",
            "access": token["access"],
            "refresh": token["refresh"],
        })
