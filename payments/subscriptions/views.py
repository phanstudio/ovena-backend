# views.py
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone
from django.db import transaction
from payments.models.subscription import Plan, Subscription, Invoice, PlanAudience, Feature, Status
from payments.services.card_service import get_default_card
from accounts.models import BusinessPayoutAccount
from .serializers import (
    SubscriptionSerializer, InvoiceSerializer, PlanSerializer, PlanCreateSerializer,
    PlanWithFeaturesSerializer, FeatureSerializer, SubscriptionCreateSerializer
)
from payments.integrations.client import client
from admin_api.views import BaseAppAdminAPIView
from business_api.views import BaseBuisAdminAPIView
from rest_framework.generics import (
    ListCreateAPIView, RetrieveUpdateAPIView, 
    RetrieveUpdateDestroyAPIView, CreateAPIView, 
    RetrieveAPIView, ListAPIView, GenericAPIView
)
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class CreateSubscriptionView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SubscriptionCreateSerializer

    def get_user_info(self, request):
        return {
            "email": request.user.email,
            # "first_name":request.user.first_name,
            # last_name:request.user.last_name,
        }
    
    def get_customer_code(self, request):
        ...
    
    def save_customer_code(self, request, paystack_customer_code):
        ...

    @transaction.atomic
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        plan_id = vd["plan_id"]
        if not plan_id:
            return Response({"error": "plan_id required"}, status=400)

        try:
            plan = Plan.objects.get(id=plan_id)
        except Plan.DoesNotExist:
            return Response({"error": "Invalid plan"}, status=404)

        # 1. Create customer in Paystack (idempotent)
        try:
            customer_code = self.get_customer_code(request)
            if not customer_code:
                customer_resp = client.create_customer( # use get customer profile for the names
                    self.get_user_info(request)
                )
                customer_code = customer_resp["data"]["customer_code"]
                if customer_code:
                    self.save_customer_code(request, customer_code)
            card = get_default_card(request.user)

        except Exception as e:
            return Response({"error": f"Paystack customer error: {e}"}, status=500)

        # 2. Create subscription in Paystack
        metadata = {
            "user_id": request.user.id,
            "plan_id": plan.id,
        }
        try:
            sub_resp = client.create_subscription(
                {
                    "customer":customer_code,
                    "plan":plan.paystack_plan_code,
                    "metadata":metadata,
                    "authorization_code": card.authorization_code
                },
            )
            sub_data = sub_resp["data"]
            print(sub_data)
        except Exception as e:
            return Response({"error": f"Paystack subscription error: {e}"}, status=500)
        
        data = {
            "subscription_code": sub_data["subscription_code"],
            "message": "Redirect user to complete payment."
        }
        if sub_data["status"] == "active":
            data["status"] = sub_data["status"]
        else:
            data["authorization_url"] = sub_data["authorization_url"]
        
        return Response(data)


class CancelSubscriptionView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        try:
            sub = Subscription.objects.select_for_update().get(
                user=request.user, active=True
            )
        except Subscription.DoesNotExist:
            return Response({"error": "No active subscription"}, status=404)

        # Cancel at Paystack (optional but recommended)
        try:
            client.disable_subscription({"code": sub.paystack_subscription_code})
        except Exception as e:
            # Log error but still deactivate locally
            logger.error("Failed to disable Paystack subscription %s: %s", 
                 sub.paystack_subscription_code, e)

        sub.active = False
        sub.cancelled_at = timezone.now()
        sub.save(update_fields=["active", "cancelled_at", "updated_at"])

        return Response({"status": "cancelled"})


class CurrentSubscriptionView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return the user's active subscription (if any)."""
        try:
            sub = Subscription.objects.select_related("plan").get(
                user=request.user, active=True
            )
            serializer = SubscriptionSerializer(sub)
            return Response(serializer.data)
        except Subscription.DoesNotExist:
            return Response({"active": False}, status=status.HTTP_200_OK)


class InvoiceHistoryView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        invoices = Invoice.objects.filter(
            subscription__user=request.user
        ).order_by("-created_at")
        serializer = InvoiceSerializer(invoices, many=True)
        return Response(serializer.data)


class ClientPlanListView(ListAPIView):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer
    permission_classes = [IsAuthenticated]


class ClientPlanDetailView(RetrieveAPIView):
    queryset = Plan.objects.all()
    serializer_class = PlanWithFeaturesSerializer
    lookup_field = "id"
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Plan.objects.prefetch_related("features").all()
        return qs


# class RetryInvoicePaymentView(GenericAPIView):
#     permission_classes = [IsAuthenticated]

#     def post(self, request, invoice_id):
#         try:
#             invoice = Invoice.objects.select_related("subscription").get(
#                 id=invoice_id,
#                 subscription__user=request.user,
#                 status=Status.FAILED,
#             )
#         except Invoice.DoesNotExist:
#             return Response({"error": "Invoice not found or not retryable"}, status=404)

#         try:
#             # resp = client.initialize_transaction({
#             #     "email": request.user.email,
#             #     "amount": invoice.amount,
#             #     "invoice_limit": 1,            # one-time charge
#             #     "subscription": invoice.subscription.paystack_subscription_code,
#             #     # this ties the payment back to the subscription
#             # })
#             resp = client.initialize_transaction({
#                 "email": request.user.email,
#                 "amount": invoice.amount,
#                 "metadata": {
#                     "invoice_id": str(invoice.id),
#                     "subscription_code": invoice.subscription.paystack_subscription_code,
#                     "retry": True,
#                 },
#                 "callback_url": settings.PAYSTACK_CALLBACK_URL,
#             })
#             resp = client.initialize_transaction({
#                 "email": request.user.email,
#                 "amount": plan.amount,
#                 "plan": plan.paystack_plan_code,  # this is the key
#                 "callback_url": settings.PAYSTACK_CALLBACK_URL,
#                 "metadata": {"user_id": request.user.id, "plan_id": plan.id}
#             })
#             return Response({"authorization_url": resp["data"]["authorization_url"]})
#         except Exception as e:
#             return Response({"error": str(e)}, status=500)


class RetryInvoicePaymentView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, invoice_id):
        try:
            invoice = Invoice.objects.select_related("subscription__plan").get(
                id=invoice_id,
                subscription__user=request.user,
                status=Status.FAILED,
            )
        except Invoice.DoesNotExist:
            return Response({"error": "Invoice not found or not retryable"}, status=404)

        subscription = invoice.subscription

        try:
            # Fetch current subscription status from Paystack
            paystack_sub = client.fetch_subscription(subscription.paystack_subscription_code)
            paystack_status = paystack_sub["data"]["status"]
        except Exception as e:
            return Response({"error": f"Could not fetch subscription status: {e}"}, status=502)

        try:
            if paystack_status in ("active", "attention"):
                # Subscription still alive at Paystack — just pay the outstanding invoice
                resp = client.initialize_transaction({
                    "email": request.user.email,
                    "amount": invoice.amount,
                    "callback_url": settings.PAYSTACK_CALLBACK_URL,
                    "metadata": {
                        "invoice_id": str(invoice.id),
                        "subscription_code": subscription.paystack_subscription_code,
                        "retry": True,
                    },
                })
            else:
                # Subscription is cancelled/completed — full re-enroll
                plan = subscription.plan
                resp = client.initialize_transaction({
                    "email": request.user.email,
                    "amount": plan.amount,
                    "plan": plan.paystack_plan_code,
                    "callback_url": settings.PAYSTACK_CALLBACK_URL,
                    "metadata": {
                        "user_id": request.user.id,
                        "plan_id": plan.id,
                    },
                })

            return Response({"authorization_url": resp["data"]["authorization_url"]})

        except Exception as e:
            return Response({"error": str(e)}, status=500)


class SubscriptionUpdateCardView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            sub = Subscription.objects.get(user=request.user, active=True)
        except Subscription.DoesNotExist:
            return Response({"error": "No active subscription"}, status=404)

        try:
            resp = client.get_subscription_update_link(sub.paystack_subscription_code)
            return Response({"update_url": resp["data"]["link"]})
        except Exception as e:
            return Response({"error": str(e)}, status=500)


# buisnesses, we might not even need all the fancy authentiction stuff
class BusinessCreateSubscriptionView(BaseBuisAdminAPIView, CreateSubscriptionView):
    # def get_user_info(self, request):
    #     return {
    #         "email": request.user.email,
    #         # "first_name":request.user.first_name,
    #         # last_name:request.user.last_name,
    #     }

    def get_customer_code(self, request):
        business_admin = self.get_buisnessadmn(request)
        payout_account = BusinessPayoutAccount.objects.filter(business_id= business_admin.business.id).first()
        if not payout_account:
            return
        return payout_account.paystack_customer_code
    
    def save_customer_code(self, request, paystack_customer_code):
        business_admin = self.get_buisnessadmn(request)
        BusinessPayoutAccount.objects.filter(
            business_id= business_admin.business.id
        ).update(paystack_customer_code= paystack_customer_code)
    ...


class BusinessCancelSubscriptionView(BaseBuisAdminAPIView, CancelSubscriptionView):
    ...


class BusinessCurrentSubscriptionView(BaseBuisAdminAPIView, CurrentSubscriptionView):
    ...


class BusinessInvoiceHistoryView(BaseBuisAdminAPIView, InvoiceHistoryView):
    ...


class BusinessPlanListView(BaseBuisAdminAPIView, ClientPlanListView):
    ...


class BusinessRetryInvoicePaymentView(BaseBuisAdminAPIView, RetryInvoicePaymentView):
    ...


class BusinessSubscriptionUpdateCardView(BaseBuisAdminAPIView, SubscriptionUpdateCardView):
    ...


# admin views
class PlanListCreateView(BaseAppAdminAPIView, ListCreateAPIView):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer

    def create(self, request, *args, **kwargs):
        # 1. Validate local data first
        current_serializer = PlanCreateSerializer
        serializer = current_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 2. Prepare Paystack plan payload
        paystack_payload = {
            "name": serializer.validated_data["name"],
            "interval": serializer.validated_data["interval"],  # 'monthly', 'yearly' etc.
            "amount": serializer.validated_data["amount"],      # already in kobo
            "description": serializer.validated_data.get("description", ""),
            "currency": "NGN",
        }

        # 3. Create plan on Paystack
        try:
            paystack_resp = client.create_plan(paystack_payload)
            paystack_plan_code = paystack_resp["data"]["plan_code"]
        except Exception as e:
            return Response(
                {"error": f"Failed to create plan on Paystack: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. Save local plan with paystack_plan_code
        plan = Plan(
            audience=serializer.validated_data["audience"],
            name=serializer.validated_data["name"],
            paystack_plan_code=paystack_plan_code,
            amount=serializer.validated_data["amount"],
            interval=serializer.validated_data["interval"],
            description=serializer.validated_data["description"],
        )
        plan.save()
        # Handle many-to-many features if provided
        if "features" in serializer.validated_data:
            plan.features.set(serializer.validated_data["features"])

        headers = self.get_success_headers(serializer.data)
        return Response(
            current_serializer(plan).data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )


class PlanDetailView(BaseAppAdminAPIView, RetrieveUpdateAPIView):
    queryset = Plan.objects.all()
    serializer_class = PlanWithFeaturesSerializer
    lookup_field = "id"

    def get_queryset(self):
        qs = Plan.objects.prefetch_related("features").all()
        return qs

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = PlanCreateSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        # Sync to Paystack (only name, description – amount cannot be changed)
        paystack_payload = {}
        if "name" in serializer.validated_data:
            paystack_payload["name"] = serializer.validated_data["name"]
        if "description" in serializer.validated_data:
            paystack_payload["description"] = serializer.validated_data["description"]

        if paystack_payload:
            try:
                client.update_plan(instance.paystack_plan_code, paystack_payload)
            except Exception as e:
                return Response(
                    {"error": f"Paystack update failed: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Save local changes
        self.perform_update(serializer)
        return Response(serializer.data)


class PlanDisableView(BaseAppAdminAPIView):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer

    def get(self, request, plan_id):
        updated = Plan.objects.filter(id=plan_id).update(audience=PlanAudience.NOONE)
        if updated == 0:
            return Response({"error": "failed to update"}, status.HTTP_400_BAD_REQUEST)
        return Response(
            {"detail": "plan disabled in the backend, kindily disable or delete in paystack"}, 
            status.HTTP_200_OK
        )


class FeatureListCreateView(BaseAppAdminAPIView, ListCreateAPIView):
    queryset = Feature.objects.all()
    serializer_class = FeatureSerializer


class FeatureDetailView(BaseAppAdminAPIView, RetrieveUpdateDestroyAPIView):
    queryset = Feature.objects.all()
    serializer_class = FeatureSerializer


class FeatureBulkCreateView(BaseAppAdminAPIView, CreateAPIView):
    queryset = Feature.objects.all()
    serializer_class = FeatureSerializer

    def get_serializer(self, *args, **kwargs):
        if isinstance(kwargs.get("data", {}), list):
            kwargs["many"] = True
        return super().get_serializer(*args, **kwargs)


# unneccessary
# class CheckFeatureView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request, feature_code):
#         """Return whether the user has a given feature."""
#         has_feature = Subscription.objects.filter(
#             user=request.user, active=True, plan__features__code=feature_code
#         ).exists()
#         return Response({"feature": feature_code, "has_feature": has_feature})

# create invoice for admin i guess or cron??
# pay for invoice??
# plan creation
# 