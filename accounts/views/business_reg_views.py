from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from accounts.models import(
    User, Business, Branch, 
    BusinessAdmin, BusinessPayoutAccount, BranchOperatingHours, BusinessCerd, BusinessOnboardStatus
)
from payments.services.base import ensure_valid_cred
from payments.integrations.paystack.errors import PaystackAPIError
from django.db import transaction, IntegrityError
from authflow.services import (
    issue_jwt_for_user, verify_phonenumber
)
from authflow.authentication import CustomBAdminAuth
from authflow.permissions import IsBusinessAdmin
from addresses.utils import checkset_location
from drf_spectacular.utils import extend_schema, inline_serializer # type: ignore
from rest_framework import serializers as s
from accounts.serializers import InS, OpS
from menu.views import BatchGenerateUploadURLView, RegisterMenusPhase3View  # noqa: F401
from common.phone.utils import get_phone_number

# edge case of going back
@extend_schema(
    responses=OpS.OnboardResponseSerializer,
)
class BusinessOnboardingStatusView(APIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]
    def get(self, request):
        Bstatus:BusinessOnboardStatus = BusinessOnboardStatus.objects.filter(admin=request.user.business_admin).first()
        
        if not Bstatus:
            data = {
                "onboarding_step": 0,
                "is_onboarding_complete": False,
            }
        else:
            data = {
            "onboarding_step": Bstatus.onboarding_step,
            "is_onboarding_complete": Bstatus.is_onboarding_complete,
        }
        response_data = OpS.OnboardResponseSerializer(data)
        return Response(response_data.data, status=status.HTTP_200_OK)

# add a update method that reqiures jwt
@extend_schema(
    responses=OpS.RegisterBAdminResponseSerializer,
    auth=[]
)
class RegisterBAdmin(GenericAPIView):
    serializer_class = InS.RegisterBAdminSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        try:
            identifier = verify_phonenumber(vd["otp_code"], get_phone_number(vd["phone_number"]), vd["pin_id"])
        except OTPInvalidError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # identifier = vd["phone_number"]
        
        try:
            with transaction.atomic():
                user = User.objects.create(
                    name=vd["full_name"],
                    phone_number=identifier,
                    email=vd["email"],
                )
                business_admin = BusinessAdmin.objects.create(user=user)
                BusinessOnboardStatus.objects.create(admin=business_admin, onboarding_step= 0)
        except IntegrityError as e:
            return Response(
                {"error": f"Registration failed due to a database constraint. Registration failed: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {"detail": f"Registration failed: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token = issue_jwt_for_user(user)

        response_data = OpS.RegisterBAdminResponseSerializer({
            "message": "User registered successfully",
            "refresh": token["refresh"],
            "access": token["access"],
            "user": {"id": user.id, "name": user.name},
        })
        return Response(response_data.data, status=status.HTTP_201_CREATED)

@extend_schema(
    auth=[]
)
class ReRegisterBAdmin(GenericAPIView):
    serializer_class = InS.RegisterBAdminSerializer
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        try:
            identifier = verify_phonenumber(vd["otp_code"], get_phone_number(vd["phone_number"]), vd["pin_id"])
        except OTPInvalidError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
      
        try:
            # identifier = vd["phone_number"]
            user = User.objects.filter(id=request.user.id).update(
                name=vd["full_name"],
                phone_number=identifier,
                email=vd["email"],
            )
        except Exception as e:
            return Response(
                {"detail": f"Registration failed: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )


        response_data = OpS.RegisterBAdminResponseSerializer({
            "message": "User Updated registered successfully",
            "user": {"id": user.id, "name": user.name},
        })
        return Response(response_data.data, status=status.HTTP_201_CREATED)

@extend_schema(
    responses={201: inline_serializer("Phase2Response", fields={
        "details": s.CharField(),
        "business_id": s.CharField(),
    })}
)
class RestaurantPhase1RegisterView(GenericAPIView):
    """
    Phase 1: Initial business + admin user registration.
    Creates: Business (bare), User (businessadmin role), BusinessAdmin link.
    No auth required — this is signup.
    """
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]
    serializer_class = InS.RestaurantPhase1Serializer
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        user = request.user

        with transaction.atomic():
            # Create the business shell
            business = Business.objects.create(
                business_name=vd["business_name"],
                business_type=vd["business_type"],
                country=vd["country"],
                business_address=vd["business_address"],
                email=vd["email"],
                phone_number=vd["phone_number"],
            )
            # if "business_image" in request.FILES:
            #     business.business_image = request.FILES["business_image"]
            # if "business_logo" in request.FILES:
            #     business.business_logo = request.FILES["business_logo"]
            BusinessCerd.objects.create(business=business)
            user.set_password(vd["password"])
            user.save()

            # Link admin to business
            business_admin = BusinessAdmin.objects.get(user=user)
            business_admin.business = business
            business_admin.save()
            BusinessOnboardStatus.objects.filter(admin=business_admin).update(onboarding_step=1)

        return Response(
            {"detail": "Business registered. Proceed to onboarding.", "business_id": business.id},
            status=status.HTTP_201_CREATED,
        )

@extend_schema(
    responses={200: inline_serializer("Phase1Response", fields={
        "details": s.CharField(),
    })}
)
class RestaurantPhase2OnboardingView(GenericAPIView):
    """
    Phase 2: Full business details — documents, image, payment, operations, branches.
    Requires the admin to be authenticated.
    """
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]
    serializer_class = InS.RestaurantPhase2Serializer
    def post(self, request):
        user = request.user
        try:
            admin = user.business_admin
        except BusinessAdmin.DoesNotExist:
            return Response({"detail": "Not a restaurant admin."}, status=status.HTTP_403_FORBIDDEN)

        restaurant:Business = admin.business
        restaurant_cerds = admin.business.cerd

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        with transaction.atomic():
            # Update restaurant details
            restaurant_cerds.registered_business_name = vd.get("registered_business_name", restaurant.business_name)
            restaurant_cerds.bn_number = vd.get("bn_number", "")
            restaurant_cerds.rc_number = vd.get("rc_number", "")
            restaurant_cerds.tax_identification_number = vd.get("tax_identification_number", "")
            restaurant_cerds.business_type = vd.get("business_type", restaurant.business_type)
            restaurant_cerds.doc_type = vd.get("doctype", "cac")

            if "business_image" in request.FILES:
                restaurant.business_image = request.FILES["business_image"]
            if "business_logo" in request.FILES:
                restaurant.business_logo = request.FILES["business_logo"]
            if "business_documents" in request.FILES:
                restaurant_cerds.business_doc = request.FILES["business_documents"]
            
            restaurant.onboarding_complete = True
            restaurant_cerds.save()
            restaurant.save()
            BusinessOnboardStatus.objects.filter(
                admin=admin
            ).update(onboarding_step=2)

            # Payment info
            payment_data = vd.get("payment", {})
            if payment_data:
                try:
                    # account_name = ensure_valid_cred(
                    #     bank_code=payment_data["bank_code"],
                    #     bank_account_number=payment_data["account_number"],
                    # )
                    account_name = payment_data["account_name"]
                except PaystackAPIError as e:
                    return Response({"error": e})
                BusinessPayoutAccount.objects.update_or_create(
                    business=restaurant,
                    defaults={
                        "bank_name": payment_data["bank"],
                        "bank_code": payment_data.get("bank_code", ""),
                        "bank_account_number": payment_data["account_number"],
                        "bank_account_name": account_name,
                        "bvn": payment_data["bvn"][-4:],
                    },
                )
            
            # Branches + operating hours
            branches_data = vd.get("branches", [])
            if len(branches_data) <= 3:
                self.sync_branches_simple(restaurant, branches_data)
            else:
                self.sync_branches_bulk(restaurant, branches_data)

        return Response({"detail": "Onboarding complete."}, status=status.HTTP_200_OK)
    
    def sync_branches_bulk(self, restaurant, branches_data):
        
        # -----------------------------------
        # FETCH EXISTING BRANCHES ONCE
        # -----------------------------------
        existing_branches = {
            (b.business_id, b.name): b
            for b in Branch.objects.filter(
                business=restaurant,
                name__in=[b["name"] for b in branches_data]
            )
        }

        branches_to_create = []
        branches_to_update = []

        for branch_data in branches_data:
            key = (restaurant.id, branch_data["name"])

            defaults = {
                "address": branch_data.get("address", "unknown"),
                "location": checkset_location(branch_data),
                "delivery_method": branch_data.get("delivery_method", "instant"),
                "pre_order_open_period": branch_data.get("pre_order_open_period"),
                "final_order_time": branch_data.get("final_order_time"),
            }

            branch = existing_branches.get(key)

            if branch:
                for field, value in defaults.items():
                    setattr(branch, field, value)

                branches_to_update.append(branch)

            else:
                branch = Branch(
                    business=restaurant,
                    name=branch_data["name"],
                    **defaults
                )

                branches_to_create.append(branch)
                existing_branches[key] = branch

        # -----------------------------------
        # BULK CREATE
        # -----------------------------------
        Branch.objects.bulk_create(branches_to_create)

        # -----------------------------------
        # BULK UPDATE
        # -----------------------------------
        Branch.objects.bulk_update(
            branches_to_update,
            fields=[
                "address",
                "location",
                "delivery_method",
                "pre_order_open_period",
                "final_order_time",
            ]
        )

        # -----------------------------------
        # REFRESH CREATED IDS
        # -----------------------------------
        all_branches = {
            b.name: b
            for b in Branch.objects.filter(
                business=restaurant,
                name__in=[b["name"] for b in branches_data]
            )
        }

        # -----------------------------------
        # OPERATING HOURS
        # -----------------------------------
        hours_to_upsert = []

        for branch_data in branches_data:
            branch = all_branches[branch_data["name"]]

            for h in branch_data.get("operating_hours", []):
                hours_to_upsert.append(
                    BranchOperatingHours(
                        branch=branch,
                        day=h["day"],
                        open_time=h["open_time"],
                        close_time=h["close_time"],
                        is_closed=h.get("is_closed", False),
                    )
                )

        BranchOperatingHours.objects.bulk_create(
            hours_to_upsert,
            update_conflicts=True,
            unique_fields=["branch", "day"],
            update_fields=["open_time", "close_time", "is_closed"],
        )

    def sync_branches_simple(self, restaurant, branches_data):
        for branch_data in branches_data:
            branch, _ = Branch.objects.update_or_create(
                business=restaurant,
                name=branch_data["name"],
                defaults={
                    "address": branch_data.get("address", "unknown"),
                    "location": checkset_location(branch_data),
                    "delivery_method": branch_data.get("delivery_method", "instant"),
                    "pre_order_open_period": branch_data.get("pre_order_open_period"),
                    "final_order_time": branch_data.get("final_order_time"),
                },
            )
            hours_data = branch_data.get("operating_hours", [])
            BranchOperatingHours.objects.bulk_create(
                [
                    BranchOperatingHours(
                        branch=branch,
                        day=h["day"],
                        open_time=h["open_time"],
                        close_time=h["close_time"],
                        is_closed=h.get("is_closed", False),
                    )
                    for h in hours_data
                ], 
                update_conflicts=True,
                unique_fields=["branch", "day"],   # 🔥 what makes a row unique
                update_fields=["open_time", "close_time", "is_closed"],  # 🔥 what to update
            )
