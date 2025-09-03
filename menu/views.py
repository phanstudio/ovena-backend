from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .serializers import (
    RestaurantSerializer, MenuItemSerializer, MenuSerializer
)
from .models import(
    Restaurant, Menu, MenuItem
)
from django.db.models import Q

class RestaurantView(APIView):
    def get(self, request):
        restaurants = Restaurant.objects.prefetch_related(
            "menus__categories__items__variant_groups__options",
            "menus__categories__items__addon_groups__addons",
            "menus__categories__items__branch_availabilities",
        )
        serializer = RestaurantSerializer(restaurants, many=True)
        return Response(serializer.data)

class MenuView(APIView):
    def get(self, request, restaurant_id):
        menus = Menu.objects.filter(restaurant_id=restaurant_id)\
                            .prefetch_related("categories__items")
        serializer = MenuSerializer(menus, many=True)
        return Response(serializer.data)

class SearchMenuItems(APIView):
    def get(self, request):
        query = request.query_params.get("q", "")
        items = MenuItem.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query) |
            Q(category__menu__restaurant__company_name__icontains=query)
        ).select_related("category__menu__restaurant")

        serializer = MenuItemSerializer(items, many=True)
        return Response(serializer.data)



# # we need to be able to get the a list of the menus, and the resturants, 
# # we need perform proper searching whether wth caching and other techniques
# # we search by categories resturants and so on?
# class Menu(APIView):
#     def get(self, request):
#         self.categories() # might not be needed
#         pass
    
#     def categories(self): # not sure if this is needed or just get from the resturants
#         MenuCategory.objects.all()
#         pass

#     # we want to get the resturant for the menus
#     # list the menus and allow searching ?
