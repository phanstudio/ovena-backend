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
    issue_jwt_for_user
)
from authflow.authentication import CustomBAdminAuth
from authflow.permissions import IsBusinessAdmin
from addresses.utils import checkset_location
from drf_spectacular.utils import extend_schema, inline_serializer # type: ignore
from rest_framework import serializers as s
from accounts.serializers import InS, OpS
from menu.views import BatchGenerateUploadURLView, RegisterMenusPhase3View  # noqa: F401

# edge case of going back
@extend_schema(
    responses=OpS.OnboardResponseSerializer,
)
class BuisnnessOnboardingStatusView(APIView):
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

        # try:
        #     identifier = verify(vd["otp_code"], vd["phone_number"])
        # except OTPInvalidError as e:
        #     return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        identifier = vd["phone_number"]
        
        try:
            with transaction.atomic():
                user = User.objects.create(
                    name=vd["full_name"],
                    phone_number=identifier,
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
    responses={201: inline_serializer("Phase2Response", fields={
        "details": s.CharField(),
        "business_id": s.CharField(),
    })}
)
class RestaurantPhase1RegisterView(GenericAPIView):
    """
    Phase 1: Initial restaurant + admin user registration.
    Creates: Business (bare), User (restaurantadmin role), BusinessAdmin link.
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
            # Create the restaurant shell
            restaurant = Business.objects.create(
                business_name=vd["business_name"],
                business_type=vd["business_type"],
                country=vd["country"],
                business_address=vd["business_address"],
                email=vd["email"],
                phone_number=vd["phone_number"],
            )
            # if "business_image" in request.FILES:
            #     restaurant.business_image = request.FILES["business_image"]
            # if "business_logo" in request.FILES:
            #     restaurant.business_logo = request.FILES["business_logo"]
            BusinessCerd.objects.create(business=restaurant)
            user.set_password(vd["password"])
            user.save()

            # Link admin to restaurant
            business_admin = BusinessAdmin.objects.get(user=user)
            business_admin.business = restaurant
            business_admin.save()
            BusinessOnboardStatus.objects.filter(admin=business_admin).update(onboarding_step=1)

        return Response(
            {"detail": "Business registered. Proceed to onboarding.", "business_id": restaurant.id},
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
            restaurant_cerds.doc_type = vd.get("doc_type", "")

            if "business_image" in request.FILES:
                restaurant.business_image = request.FILES["business_image"]
            # if "business_logo" in request.FILES:
            #     restaurant.business_logo = request.FILES["business_logo"]
            if "business_documents" in request.FILES:
                restaurant_cerds.business_doc = request.FILES["business_documents"]
            
            restaurant.onboarding_complete = True
            restaurant_cerds.save()
            restaurant.save()
            BStatus:BusinessOnboardStatus = BusinessOnboardStatus.objects.get(admin=admin)
            BStatus.onboarding_step = 2
            BStatus.save()

            # Payment info
            payment_data = vd.get("payment", {})
            if payment_data:
                try:
                    # account_name = ensure_valid_cred(
                    #     bank_code=payment_data["bank_code"],
                    #     bank_account_number=payment_data["account_number"],
                    # )
                    account_name = vd["account_number"]
                except PaystackAPIError as e:
                    return Response({"error": e})
                BusinessPayoutAccount.objects.update_or_create(
                    business=restaurant,
                    defaults={
                        "bank_name": payment_data["bank"],
                        "bank_code": payment_data.get("bank_code", ""),
                        "account_number": payment_data["account_number"],
                        "account_name": account_name,
                        "bvn": payment_data["bvn"][-4:],
                    },
                )
                
                # ── Bank account verification via Paystack ──
                # bank_code should come from a banks list endpoint (Paystack /bank)
                # For now, accept it as an optional field alongside account_number
                # bank_result = {}#verify_bank_account_paystack(data["account_number"], bank_code)
                # bank_account.is_verified = True#bank_result["success"]
                # bank_account.verified_at = timezone.now()
                # bank_account.save()

                # UserAccount.objects.update_or_create(
                #     user=user,
                #     defaults={
                #         "bank_account_name": payment_data["bank"],
                #         "bank_code": payment_data.get("bank_code", ""),
                #         "bank_account_number": payment_data["account_number"],
                #         "account_name": payment_data["account_name"],
                #         "bvn": payment_data["bvn"][-4:],
                #     },
                # )
                # paystack_recipient_code = models.CharField(max_length=100, blank=True)
                # updated_at = models.DateTimeField(auto_now=True)

                        
            
            # Branches + operating hours
            branches_data = vd.get("branches", [])
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
                    # business=restaurant,
                    # name=branch_data["name"],
                    # address=branch_data.get("address", "unknown"),
                    # location=checkset_location(branch_data),
                    # delivery_method=branch_data.get("delivery_method", "instant"),
                    # pre_order_open_period=branch_data.get("pre_order_open_period"),
                    # final_order_time=branch_data.get("final_order_time"),
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

        return Response({"detail": "Onboarding complete."}, status=status.HTTP_200_OK)

