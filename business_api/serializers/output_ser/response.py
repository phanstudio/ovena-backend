from rest_framework import serializers
from accounts.models import (
    Branch, PrimaryAgent
)
from addresses.serializers import LocationFieldMixin

class BranchlistSerializer(LocationFieldMixin, serializers.ModelSerializer):
    location = serializers.SerializerMethodField()
    class Meta:
        model = Branch
        fields = [
            "id",
            "name",
            "created_at",
            "address",
            "location"
        ]

class PrimaryAgentBranchSerializer(LocationFieldMixin, serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    branch_id = serializers.IntegerField(source="branch.id", read_only=True)
    branch_address = serializers.CharField(source="branch.address", read_only=True)
    branch_location = serializers.SerializerMethodField(method_name="get_location")
    location_field = "branch.location"
    user_name = serializers.CharField(source="user.name", read_only=True)

    class Meta:
        model = PrimaryAgent
        fields = [
            "id",           # primary agent id
            "device_name",
            "user_name",    # optional, can show the user name
            "branch_id",
            "branch_name",
            "branch_location",
            "branch_address"
        ]

class BuisnessResponse(serializers.Serializer):
    detail = serializers.CharField()