from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from accounts.serializers import (
    CustomerProfileSerializer, DriverProfileSerializer,
    RestaurantProfileSerializer, RegisterCustomerSerializer,
)
from accounts.models import(
    User, Restaurant, Address, Branch, DriverProfile
)
from django.db import transaction

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

        elif user.role == "restaurant":
            profile = getattr(user, "restaurant_profile", None)
            if not profile:
                return Response({"detail": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)
            serializer = RestaurantProfileSerializer(profile)

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
                    latitude=lat,
                    longitude=long,
                )
                # Create restaurant profile
                restaurant = Restaurant.objects.create(
                    # certification=certification,
                    bn_number=bn_number,
                    company_name=company_name,
                )
                Branch.objects.create(
                    restaurant= restaurant,
                    location=location,
                    phone_number=phone_number,
                    name=branch_name
                )

            return Response({"detail": "successful"}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {"detail": f"registration failed: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

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

class RegisterCustomer(APIView): # expecting a jwt token before registering the user
    # if we add this and truly thers a case where that is optional then we fix it
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = RegisterCustomerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "successful"}, status=status.HTTP_201_CREATED)
