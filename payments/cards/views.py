from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from payments.integrations.client import client
from rest_framework.generics import (
    GenericAPIView, ListAPIView
)
from payments.models.card import CardAuthorization
from .serializers import CardAuthorizationSerializer, SetPrimaryCardSerializer
from rest_framework import status
from payments.services.card_service import set_primary_card
import logging
from business_api.views import BaseBuisAdminAPIView

logger = logging.getLogger(__name__)


class SaveCardView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_metadata(self, data, request):
        return data

    def post(self, request):
        payer = request.user
        email = payer.email
        error = ""
        data = {
            "card_saving": True,
            "user_id": payer.id
        }
        for i in [1_000, 5_000, 10_000]:
            try:
                payload = {
                    "email": email,
                    "amount": i,
                    "metadata": self.get_metadata(data, request),
                    "channel": "card",
                    "callback_url": "https://ovena-backend-production.up.railway.app/api/payments/paystack/callback/",
                }
                data = client.initialize_transaction(payload).get("data", {})
                return Response({"data": data})
            except Exception as e:
                print(str(e))
                error = str(e)
                continue
        return Response({"error": error}, status=500)


class ListCardsView(ListAPIView):
    serializer_class = CardAuthorizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CardAuthorization.objects.filter(user=self.request.user)


class SetPrimaryCardView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SetPrimaryCardSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        card_id = vd["card_id"]
        try:
            card = CardAuthorization.objects.get(
                id=card_id,
                user=request.user
            )
        except CardAuthorization.DoesNotExist:
            return Response(
                {"error": "Card not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        set_primary_card(card)

        return Response({
            "message": "Primary card updated successfully"
        })


class BusinessSaveCardView(BaseBuisAdminAPIView, SaveCardView):

    def get_metadata(self, data, request):
        business_admin = self.get_buisnessadmn(request)
        if not business_admin.business: raise ValueError("Use a valid business admin wiht a business.")
        data["business_id"] = business_admin.business.id
        return data
    ...


class BusinessListCardsView(BaseBuisAdminAPIView, ListCardsView):
    ...


class BusinessSetPrimaryCardView(BaseBuisAdminAPIView, SetPrimaryCardView):
    ...
