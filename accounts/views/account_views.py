from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from accounts.serializer import (
    CustomerProfileSerializer, DriverProfileSerializer,
    RestaurantProfileSerializer
)
from accounts.models import(
    User, Employee, Restaurant, Address, Branch
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

class RegisterUser(APIView):
    def post(self, request):
        phone_number = request.data.get("phone_number")
        lat = request.data.get("lat")   # ✅ fixed (was swapped in your code)
        long = request.data.get("long")
        bn_number = request.data.get("bn_number")
        company_name = request.data.get("company_name")
        branch_name = request.data.get("branch_name")

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
