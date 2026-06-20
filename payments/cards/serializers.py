from rest_framework import serializers
from payments.models.card import CardAuthorization

class CardAuthorizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CardAuthorization
        fields = [
            "id",
            "last4",
            "exp_month",
            "exp_year",
            "brand",
            "primary_card",
        ]

class SetPrimaryCardSerializer(serializers.Serializer):
    card_id = serializers.IntegerField()
