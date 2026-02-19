# app/storage_backends.py
from django.core.files.storage import storages

class PrivateStorage:
    def __new__(cls, *args, **kwargs):
        return storages["private"]

# use case

# from django.db import models
# from .storage_backends import PrivateStorage

# class Restaurant(models.Model):
#     logo = models.ImageField(upload_to="restaurants/logos/", blank=True, null=True)  # public (default)
#     registration_doc = models.FileField(
#         upload_to="restaurants/docs/",
#         storage=PrivateStorage(),  # private bucket
#         blank=True,
#         null=True
#     )


# from rest_framework import serializers
# from .models import Restaurant

# class RestaurantSerializer(serializers.ModelSerializer):
#     logo_url = serializers.SerializerMethodField()
#     registration_doc_url = serializers.SerializerMethodField()

#     class Meta:
#         model = Restaurant
#         fields = ["id", "logo_url", "registration_doc_url"]

#     def get_logo_url(self, obj):
#         return obj.logo.url if obj.logo else None

#     def get_registration_doc_url(self, obj):
#         # Only return private doc URL if the requester is allowed
#         request = self.context.get("request")
#         if not request or not request.user.is_authenticated:
#             return None
#         # add your permission logic here (owner/admin/etc.)
#         return obj.registration_doc.url if obj.registration_doc else None
