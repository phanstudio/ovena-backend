from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from accounts.serializers import (
    CustomerProfileSerializer, DriverProfileSerializer,
    CreateCustomerSerializer, UpdateCustomerSerializer,
    BuisnessAdminProfileSerializer
)
from accounts.models import(
    User, Business, Address, Branch, DriverProfile, PrimaryAgent, LinkedStaff, BusinessAdmin
)
from django.db import transaction, IntegrityError
from authflow.services import create_token, issue_jwt_for_user, verify, OTPInvalidError, request_phone_otp
from django.contrib.gis.geos import Point
from authflow.authentication import CustomCustomerAuth

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
        return Response({"detail": "User account deleted."}, status=status.HTTP_200_OK)

class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]
    def delete(self, request):
        user = request.user
        user.delete()
        return Response({"detail": "User account deleted."}, status=status.HTTP_200_OK)

# class RegisterResturant(APIView):
#     def post(self, request):
#         phone_number = request.data.get("phone_number")
#         lat = request.data.get("lat")   # ✅ fixed (was swapped in your code)
#         long = request.data.get("long")
#         bn_number = request.data.get("bn_number")
#         company_name = request.data.get("company_name")
#         branch_name = request.data.get("branch_name") or "main"

#         try:
#             with transaction.atomic():
#                 # Create address
#                 location = Address.objects.create(
#                     address="unknown",
#                     location=Point(long, lat, srid=4326)
#                 )
#                 business = Business.objects.create(
#                     # certification=certification,
#                     bn_number=bn_number,
#                     business_name=company_name,
#                     business_type="restaurant",
#                     phone_number=phone_number or "",
#                 )
#                 Branch.objects.create(
#                     business=business,
#                     address=getattr(location, "address", "unknown"),
#                     location=getattr(location, "location", None),
#                     name=branch_name
#                 )

#             return Response({"detail": "successful"}, status=status.HTTP_201_CREATED)

#         except Exception as e:
#             return Response(
#                 {"detail": f"registration failed: {str(e)}"},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

class RegisterResturant(APIView):
    def post(self, request):
        phone_number = request.data.get("phone_number")
        lat = request.data.get("lat")   # ✅ fixed (was swapped in your code)
        long = request.data.get("long")
        bn_number = request.data.get("bn_number")
        company_name = request.data.get("company_name")
        branch_name = request.data.get("branch_name") or "main"

        try:
            with transaction.atomic():
                # Create address
                location = Address.objects.create(
                    address="unknown",
                    location=Point(long, lat, srid=4326)
                )
                business = Business.objects.create(
                    # certification=certification,
                    bn_number=bn_number,
                    business_name=company_name,
                    business_type="restaurant",
                    phone_number=phone_number or "",
                )
                Branch.objects.create(
                    business=business,
                    address=getattr(location, "address", "unknown"),
                    location=getattr(location, "location", None),
                    name=branch_name
                )

            return Response({"detail": "successful"}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {"detail": f"registration failed: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )


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

class RegisterRAdmin(APIView):
    permission_classes = []

    def post(self, request): # verify otp
        fullname = request.data.get("full_name")
        phone_number = request.data.get("phone_number")
        # country = request.data.get("country")
        # business_address = 
        otp_code = request.data.get("otp_code")

        if not phone_number or not otp_code or not fullname:
            return Response({"error": "Phone number, OTP and Full Name are required;\
                              full_name:full_name, phone_number:phone_number, \
                             otp_code:otp_code"}, status=status.HTTP_400_BAD_REQUEST)

        identifier = ""
        try:
            identifier = verify(otp_code, phone_number)
        except OTPInvalidError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)        

        try:
            with transaction.atomic():
                user = User.objects.create(name=fullname, phone_number=identifier, role="BusinessAdmin")
                # business = Business.objects.create(country=country, )
                # BusinessAdmin.objects.create(user=user, business=business)

        except IntegrityError as e:
            # Handle specific uniqueness violations
            if "unique" in str(e).lower():
                return Response(
                    {"error": "Username or phonenumber already taken"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # return Response(
            #     {"error": "Branch not found or was removed during creation"},
            #     status=status.HTTP_400_BAD_REQUEST,
            # )

        # main_token = create_token(user, role="main", expires_in=3600)

        # ✅ Issue JWT tokens
        token = issue_jwt_for_user(user)
        return Response({
            "message": "User registered successfully",
            "refresh": token["refresh"],
            "access": token["access"],
            "user": {"id": user.id, "name": user.name},
        }, status=status.HTTP_201_CREATED)



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


