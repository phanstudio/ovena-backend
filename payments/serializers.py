from rest_framework import serializers
from payments.models import Bank

class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = [
            "id",
            "country",
            "code",
            "name",
            "active",
        ]
