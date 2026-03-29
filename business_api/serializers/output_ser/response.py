from rest_framework import serializers
from accounts.models import (
    Branch, PrimaryAgent
)

class BranchlistSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = [
            "id",
            "name",
            "created_at",
        ]

class PrimaryAgentBranchSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    branch_id = serializers.IntegerField(source="branch.id", read_only=True)
    branch_location = serializers.SerializerMethodField()
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
        ]

    def get_branch_location(self, obj):
        # Returns a dict of lat/lng
        if obj.branch.location:
            return {
                "latitude": obj.branch.location.y,
                "longitude": obj.branch.location.x,
            }
        return None

class BuisnessResponse(serializers.Serializer):
    detail = serializers.CharField()