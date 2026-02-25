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
    User, Business, Branch, DriverProfile, PrimaryAgent, 
    BusinessAdmin, BusinessPayoutAccount, BranchOperatingHours, BusinessCerd
)
from django.db import transaction, IntegrityError
from authflow.services import create_token, issue_jwt_for_user, verify, OTPInvalidError, request_phone_otp
from django.contrib.gis.geos import Point
from authflow.authentication import CustomCustomerAuth, CustomBAdminAuth
from authflow.permissions import IsBusinessAdmin
from addresses.utils import checkset_location
from drf_spectacular.utils import extend_schema, inline_serializer # type: ignore
from rest_framework import serializers as s

from accounts.serializers import InS, OpS

class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.role == "customer": # repating can be a single function
            profile = getattr(user, "customer_profile", None)
            if not profile:
                return Response({"detail": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)
            serializer = CustomerProfileSerializer(profile)

        elif user.role == "driver":
            profile = getattr(user, "driver_profile", None)
            if not profile:
                return Response({"detail": "Driver profile not found."}, status=status.HTTP_404_NOT_FOUND)
            serializer = DriverProfileSerializer(profile)
            # might add the resturant owners
        elif user.role == "businessadmin":
            profile = getattr(user, "business_admin", None)
            if not profile:
                return Response({"detail": "Business Admin profile not found."}, status=status.HTTP_404_NOT_FOUND)
            serializer = BuisnessAdminProfileSerializer(profile)
            # might add the resturant owners
        elif user.role == "buisnessstaff":
            profile = getattr(user, "primary_agent", None)
            if not profile:
                return Response({"detail": "Primary Agent profile not found."}, status=status.HTTP_404_NOT_FOUND)
            serializer = PrimaryAgentProfileSerializer(profile)
            # might add the resturant owners
        else:
            return Response({"detail": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "user": {
                "id": user.id,
                "email": user.email,
                "phone_number": user.phone_number,
                "name": user.name,
                "role": user.role,
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


# register resturant
# finished
# due to new opt code this is depeciated will use a different method
# class LinkRequestCreate(APIView):
#     permission_classes = [IsAuthenticated]#IsAuthenticated, IsResturantManager]
#     def post(self, request):
#         user = request.user
#         # return request_phone_otp()
#         # otp = send_otp(user.id)
#         # return Response({"otp": otp})

# class LinkApprove(APIView):
#     authentication_classes = []  # mobile only
#     def post(self, request):
#         otp = request.data.get("otp")
#         device_id = request.data.get("device_id")
#         if not otp or not device_id:
#             return Response({"detail": "Otp or Device id not found."}, status=status.HTTP_404_NOT_FOUND)
#         # user_id = verify_otp(otp)
#         user_id = 1

#         # Fetch PrimaryAgent in one query
#         primary_agent = (
#             PrimaryAgent.objects
#             .select_related("user", "branch")
#             .filter(user_id=user_id)
#             .first()
#         )
#         if not primary_agent:
#             return Response(
#                 {"detail": "User not a manager."},
#                 status=status.HTTP_404_NOT_FOUND
#             )
#         sub_user = LinkedStaff.objects.create(
#             created_by= primary_agent,
#             device_name=device_id
#         )
#         user = {"user_id": primary_agent.user.id, "device_id": device_id}
#         sub_token = create_token(user, role="sub", scopes=["read", "availability:update", "item:availability"]) 
#         # create a ascopes modules /class contain the available scopes also i'm i just reenventing the wheel that permissions can solve?
#         return Response(
#             {
#                 "message": "Account registered successfully",
#                 "user": {
#                     "id": sub_user.id,
#                     "username": sub_user.device_name,
#                 },
#                 "tokens": sub_token
#             },
#             status=status.HTTP_201_CREATED,
#         )

# fuse rr and rrm add main
# adi attached to the resturants, handeling withdrawals, added vendors.
# tokens system for paymets.
# optional address names?

class RegisterRManager(APIView):
    permission_classes = []

    def post(self, request):
        username = request.data.get("username")
        email = request.data.get("email")
        branch_id = request.data.get("branch_id")

        if not username or not branch_id:
            return Response(
                {"error": "Username and branch are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                user = User.objects.create(name=username, email=email)
                PrimaryAgent.objects.create(user=user, branch_id=branch_id)

        except IntegrityError as e:
            # Handle specific uniqueness violations
            # if "unique" in str(e).lower():
            #     return Response(
            #         {"error": "Username or branch already taken"},
            #         status=status.HTTP_400_BAD_REQUEST,
            #     )
            return Response(
                {"error": "Branch not found or was removed during creation"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        main_token = create_token(user, role="main", expires_in=3600)

        return Response(
            {
                "message": "User registered successfully",
                "user": {"id": user.id, "name": user.name},
                "tokens": main_token,
            },
            status=status.HTTP_201_CREATED,
        )

# add transfer of ownershp later


# regular register
class RegisterDrivers(APIView): # what is the flow for drivers
    permission_classes = [IsAuthenticated]
    # review the drives credentials after a few days
    def post(self, request):
        phone = request.data.get("phone_number")
        email = request.data.get("email")
        nin = request.data.get("nin")
        plate_number = request.data.get("plate_number")
        vehicle_type = request.data.get("vehicle_type")
        photo = request.data.get("photo")
        name = request.data.get("name")

        try:
            # as a driver phone numbr is manditory
            with transaction.atomic():

                if email:
                    user = User.objects.filter(email=email).first()
                if phone:
                    if not user:
                        user = User.objects.filter(phone_number=phone).first()
                    else:
                        user.phone_number = phone
                        user.save(update_fields=["phone_number"])
                else:
                    pass
                
                if name:
                    user.name = name
                    user.save(update_fields=["name"])

                # get or create profile
                profile, created = DriverProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "nin": nin,
                        "plate_number": plate_number,
                        "vehicle_type": vehicle_type,
                        "photo":photo,
                    },
                )

                if not created:
                    updates = {}
                    if nin:
                        updates["nin"] = nin # create a service to validate the nin
                    if plate_number:
                        updates["plate_number"] = plate_number # create a service to validate the plate number
                    if vehicle_type:
                        updates["vehicle_type"] = vehicle_type # create a service to validate the vehicle type
                    if photo:
                        updates["photo"] = photo # create a service to validate info through the photo and the info provided
                    
                    if updates:
                        for field, value in updates.items():
                            setattr(profile, field, value)
                        profile.save(update_fields=list(updates.keys()))

            return Response({"detail": "successful"}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {"detail": f"registration failed: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

class RegisterCustomer(APIView):
    authentication_classes = [CustomCustomerAuth]
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
            identifier = verify(vd["otp_code"], vd["phone_number"])
        except OTPInvalidError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.create(
                name=vd["full_name"],
                phone_number=identifier,
                role="businessadmin"
            )
        except IntegrityError as e:
            if "unique" in str(e).lower():
                return Response(
                    {"error": "Username or phonenumber already taken"},
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
            BusinessCerd.objects.create(business=restaurant)
            user.set_password(vd["password"])
            user.save()

            # Link admin to restaurant
            BusinessAdmin.objects.create(business=restaurant, user=user)

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
            if "business_documents" in request.FILES:
                restaurant_cerds.business_doc = request.FILES["business_documents"]
            
            restaurant.onboarding_complete = True
            restaurant_cerds.save()
            restaurant.save()

            # Payment info
            payment_data = vd.get("payment", {})
            if payment_data:
                BusinessPayoutAccount.objects.update_or_create(
                    business=restaurant,
                    defaults={
                        "bank_name": payment_data["bank"],
                        "account_number": payment_data["account_number"],
                        "account_name": payment_data["account_name"],
                        "bvn": payment_data["bvn"][-4:],
                    },
                )
            
            # Branches + operating hours
            branches_data = vd.get("branches", [])
            for branch_data in branches_data:
                branch = Branch.objects.create(
                    business=restaurant,
                    name=branch_data["name"],
                    address=branch_data.get("address", "unknown"),
                    location=checkset_location(branch_data),
                    delivery_method=branch_data.get("delivery_method", "instant"),
                    pre_order_open_period=branch_data.get("pre_order_open_period"),
                    final_order_time=branch_data.get("final_order_time"),
                )

                hours_data = branch_data.get("operating_hours", [])
                BranchOperatingHours.objects.bulk_create([
                    BranchOperatingHours(
                        branch=branch,
                        day=h["day"],
                        open_time=h["open_time"],
                        close_time=h["close_time"],
                        is_closed=h.get("is_closed", False),
                    )
                    for h in hours_data
                ])

        return Response({"detail": "Onboarding complete."}, status=status.HTTP_200_OK)


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
            payment = admin.business.payment
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
            restaurant=admin.business,
            defaults={
                "bank_name": vd["bank"],
                "account_number": vd["account_number"],
                "account_name": vd["account_name"],
                "bvn": vd["bvn"],
            },
        )
        return Response({"detail": "Payment info updated."})

# @extend_schema(auth=[])
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

        user = User.objects.filter(
            phone_number=vd["phone_number"],
            role="driver"
        ).first()
        
        driver_profile = getattr(user, "driver_profile", None)
        if not driver_profile:
            return Response(
                {"error": "Driver profile missing"},
                status=status.HTTP_403_FORBIDDEN
            )

        if not driver_profile.is_approved:
            return Response(
                {"error": "Account pending approval"},
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

        user = User.objects.filter(
            phone_number=vd["phone_number"],
            role="businessadmin"
        ).first()
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
