from rest_framework import serializers
from accounts.models import (
    Branch
)

class BranchlistSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = [
            "id",
            "name",
            "created_at",
        ]