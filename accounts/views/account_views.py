from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from accounts.serializers import (
    CustomerProfileSerializer,
    DriverProfileSerializer,
    CreateCustomerSerializer,
    UpdateCustomerSerializer,
    BuisnessAdminProfileSerializer,
    PrimaryAgentProfileSerializer,
    Delete2Serializer,
)
from accounts.models import (
    User,
    Branch,
    PrimaryAgent,
)
from admin_api.models import AppAdmin
from django.db import transaction, IntegrityError
from authflow.services import issue_jwt_for_user, verify, OTPInvalidError, OTPManager
from authflow.authentication import CustomCustomerAuth, CustomBAdminAuth
from authflow.permissions import IsBusinessAdmin
from accounts.services.roles import get_user_roles
from accounts.services.profiles import PROFILE_BUSINESS_ADMIN, get_profile
from drf_spectacular.utils import extend_schema, inline_serializer  # type: ignore
from rest_framework import serializers as s
from accounts.serializers import InS, OpS
from authflow.services.phone_number import get_phone_number
from django.db.models import Count, Q


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
                return Response(
                    {"detail": "Customer profile not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            serializer = CustomerProfileSerializer(profile)
        elif requested_type == "driver":
            profile = getattr(user, "driver_profile", None)
            if not profile:
                return Response(
                    {"detail": "Driver profile not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            serializer = DriverProfileSerializer(profile)
        elif requested_type == "businessadmin":
            profile = getattr(user, "business_admin", None)
            if not profile:
                return Response(
                    {"detail": "Business Admin profile not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            serializer = BuisnessAdminProfileSerializer(profile)
        elif requested_type in ("businessstaff", "buisnessstaff"):
            profile = getattr(user, "primary_agent", None)
            if not profile:
                return Response(
                    {"detail": "Primary Agent profile not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
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
        elif getattr(user, "primary_agent", None):
            serializer = PrimaryAgentProfileSerializer(user.primary_agent)
            active_profile_type = "businessstaff"
        else:
            return Response(
                {"detail": "No profile found for this user."},
                status=status.HTTP_404_NOT_FOUND,
            )
        userserializer = OpS.UserSerializer(user)
        return Response(
            {
                "user": userserializer.data,
                "roles": user_roles,
                "active_profile_type": active_profile_type,
                "profile": serializer.data,
            }
        )


class Delete2AccountView(GenericAPIView):
    serializer_class = Delete2Serializer

    def delete(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        User.objects.filter(id=vd["user_id"]).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeleteAccountView(APIView):  # will change to a soft delete
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)  # remove the delete later


@extend_schema(
    responses={
        200: inline_serializer(
            "LinkRequestCreateResponse", fields={"otp": s.CharField()}
        )
    },
)
class LinkRequestCreateView(GenericAPIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]
    serializer_class = InS.LinkRequestSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        user = request.user
        otp = OTPManager.send_blank(
            f"{get_phone_number(user)};{vd['branch_id']}"
        )  # or id since it can be auto gen
        return Response({"otp": otp})


# might add password
# check if the user is not revocked
# add delete linked user
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

        # 🔐 Step 1: Verify OTP
        try:
            identifier = OTPManager.verify(otp_code=vd["otp"])
        except OTPInvalidError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        phone_number, branch_id = identifier.split(";")

        # 🔒 Step 2: Atomic block with row locking
        with transaction.atomic():
            branch = (
                Branch.objects.select_related("business__admin__user")
                .select_for_update()  # 🔥 prevents race conditions
                .filter(id=branch_id, business__admin__user__phone_number=phone_number)
                .first()
            )

            if not branch:
                return Response(
                    {"detail": "Invalid branch or not authorized"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            business_admin = branch.business.admin

            # 👤 Step 3: Get or create user
            # user, _ = User.objects.get_or_create(
            #     phone_number=vd["phone_number"],
            #     defaults={"name": vd["username"] or device_id},
            # )

            # 🔍 Step 4: Handle PrimaryAgent safely
            existing_agent = getattr(branch, "primary_agent", None)

            if existing_agent:
                if not existing_agent.revoked:
                    return Response(
                        {"detail": "Branch already has an active primary agent"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # ♻️ Reuse revoked agent
                # existing_agent.user = user
                existing_agent.device_name = device_id
                existing_agent.revoked = False
                existing_agent.revoked_at = None
                existing_agent.created_by = business_admin
                existing_agent.save()

                user = existing_agent.user  # ✅ reuse existing identity
                user.name = vd["username"] or device_id
                user.phone_number = vd["phone_number"]
                user.save()

                sub_user = existing_agent

            else:
                # ✅ Safe to create
                sub_user = PrimaryAgent.objects.create(
                    created_by=business_admin,
                    device_name=device_id,
                    branch=branch,
                    user=user,
                )

        # 🔑 Step 5: Issue token
        token = issue_jwt_for_user(user)

        response = OpS.RegisterBAdminResponseSerializer(
            {
                "message": "Account registered successfully",
                "refresh": token["refresh"],
                "access": token["access"],
                "user": {
                    "id": sub_user.id,
                    "name": sub_user.device_name,
                },
            }
        )

        return Response(response.data, status=status.HTTP_201_CREATED)


# class LinkApproveView(GenericAPIView):
#     serializer_class = InS.LinkApproveSerializer
#     permission_classes = [AllowAny]

#     def post(self, request):
#         serializer = self.get_serializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         vd = serializer.validated_data

#         device_id = vd["device_id"]

#         try:
#             identifier = OTPManager.verify(otp_code=vd["otp"])
#         except OTPInvalidError as e:
#             return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

#         phone_number, branch_id = identifier.split(";")

#         branch = (
#             Branch.objects.select_related("business__admin__user")
#             .annotate(
#                 active_agent_count=Count(
#                     "primary_agent", filter=Q(primary_agent__revoked=False)
#                 )
#             )
#             .filter(id=branch_id, business__admin__user__phone_number=phone_number)
#             .first()
#         )

#         if not branch:
#             return Response({"detail": "Invalid branch or not authorized"}, status=403)

#         if branch.active_agent_count > 0:
#             return Response(
#                 {"detail": "Branch already has an active primary agent"}, status=400
#             )

#         business_admin = branch.business.admin

#         try:
#             with transaction.atomic():
#                 user, _ = User.objects.get_or_create(
#                     phone_number=vd["phone_number"],
#                     defaults={"name": vd["username"] or device_id},
#                 )

#                 sub_user = PrimaryAgent.objects.create(
#                     created_by=business_admin,
#                     device_name=device_id,
#                     branch=branch,
#                     user=user,
#                 )

#         except IntegrityError as _:
#             return Response(
#                 {"error": "A device_id is already linked"},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         token = issue_jwt_for_user(user)
#         response = OpS.RegisterBAdminResponseSerializer(
#             {
#                 "message": "Account registered successfully",
#                 "refresh": token["refresh"],
#                 "access": token["access"],
#                 "user": {"id": sub_user.id, "name": sub_user.device_name},
#             }
#         )
#         return Response(
#             response.data,
#             status=status.HTTP_201_CREATED,
#         )


# add transfer of ownershp later
class RegisterCustomer(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateCustomerSerializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Customer registered successfully"},
            status=status.HTTP_201_CREATED,
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


# app admin
@extend_schema(
    responses={
        200: inline_serializer(
            "LinkRequestCreateResponse", fields={"otp": s.CharField()}
        )
    },
)
class AppAdminRequestCreateView(GenericAPIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]
    serializer_class = InS.AppAdminRequestSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        otp = OTPManager.send_blank(f"{vd['role']}")
        return Response({"otp": otp})


@extend_schema(
    responses=OpS.RegisterBAdminResponseSerializer,
    auth=[],
)
class AppAdminApproveView(GenericAPIView):
    serializer_class = InS.AppAdminApproveSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        try:
            identifier = OTPManager.verify(otp_code=vd["otp"])
        except OTPInvalidError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    name=vd["full_name"],
                    phone_number=vd["phone_number"],
                    email=vd["email"],
                    password=vd["password"],
                )
                AppAdmin.objects.create(user=user, role=identifier)
        except IntegrityError as e:
            return Response(
                {
                    "error": f"Registration failed due to a database constraint. Registration failed: {str(e)}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {"detail": f"Registration failed: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token = issue_jwt_for_user(user)
        response = OpS.RegisterBAdminResponseSerializer(
            {
                "message": "Account registered successfully",
                "refresh": token["refresh"],
                "access": token["access"],
                "user": {"id": user.id, "name": user.name},
            }
        )
        return Response(
            response.data,
            status=status.HTTP_201_CREATED,
        )


# Login views
@extend_schema(
    responses={
        200: inline_serializer(
            "DriverLoginResponse",
            fields={
                "message": s.CharField(),
                "access": s.CharField(),
                "refresh": s.CharField(),
            },
        )
    },
    auth=[],
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
                {"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )

        driver_profile = getattr(user, "driver_profile", None)
        if not driver_profile:
            return Response(
                {"error": "Driver profile missing"}, status=status.HTTP_403_FORBIDDEN
            )

        # if not driver_profile.is_approved:
        #     return Response(
        #         {"error": "Account pending approval"},
        #         status=status.HTTP_403_FORBIDDEN
        #     )

        if not user or not user.check_password(vd["password"]):
            return Response(
                {"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )

        token = issue_jwt_for_user(user)
        return Response(
            {
                "message": "Logged in successfully",
                "access": token["access"],
                "refresh": token["refresh"],
            }
        )


@extend_schema(
    responses={
        200: inline_serializer(
            "AdminLoginResponse",
            fields={
                "message": s.CharField(),
                "access": s.CharField(),
                "refresh": s.CharField(),
            },
        )
    },
    auth=[],
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
                {"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )
        buisness_admin_role = get_profile(user, PROFILE_BUSINESS_ADMIN)
        if not buisness_admin_role:
            return Response(
                {"error": "Not a business admin account"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not user or not user.check_password(vd["password"]):
            return Response(
                {"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )

        token = issue_jwt_for_user(user)
        return Response(
            {
                "message": "Logged in successfully",
                "access": token["access"],
                "refresh": token["refresh"],
            }
        )


@extend_schema(
    responses={
        200: inline_serializer(
            "AdminChangePasswordResponse",
            fields={
                "message": s.CharField(),
            },
        )
    },
)
class ChangePasswordView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InS.ChangePasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        user: User = request.user
        if user.check_password(vd["password"]):
            return Response(
                {"error": "Invalid password"}, status=status.HTTP_401_UNAUTHORIZED
            )

        user.set_password(vd["new_password"])
        user.save(update_fields=["password"])
        return Response({"message": "Password Changed"})


@extend_schema(
    responses={
        200: inline_serializer(
            "PasswordResetResponse",
            fields={
                "message": s.CharField(),
            },
        )
    },
    auth=[],
)
class PasswordResetView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = InS.PasswordResetSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        # try:
        #     identifier = verify(vd["otp_code"], vd["phone_number"])
        # except OTPInvalidError as e:
        #     return Response({"error": str(e)}, status=400)
        identifier = vd["phone_number"]

        user = User.objects.filter(phone_number=identifier).first()
        if not user:
            return Response({"error": "User not found"}, status=404)

        user.set_password(vd["new_password"])
        user.save(update_fields=["password"])

        # force re-login on all devices
        # if you store a token version on the user model you can invalidate all JWTs
        # simplest approach: tell frontend to discard tokens and re-login
        # force login flow

        return Response({"message": "Password updated successfully"})


@extend_schema(auth=[])
class StaffLoginView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = InS.LinkStaffLoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        device_id = vd["device_id"]  # migth add branch_id
        buisness_staff = (
            PrimaryAgent.objects.filter(device_name=device_id)
            .select_related("user")
            .first()
        )
        user = buisness_staff.user

        if not buisness_staff:
            return Response(
                {"error": "Account doesn't exist"}, status=status.HTTP_403_FORBIDDEN
            )

        if buisness_staff.revoked:
            return Response(
                {"error": "Account revoked"}, status=status.HTTP_403_FORBIDDEN
            )

        # if not user or not user.check_password(vd["password"]): # add this later after we remove
        #     return Response(
        #         {"error": "Invalid credentials"},
        #         status=status.HTTP_401_UNAUTHORIZED
        #     )

        token = issue_jwt_for_user(user)
        return Response(
            {
                "message": "Logged in successfully",
                "access": token["access"],
                "refresh": token["refresh"],
            }
        )
