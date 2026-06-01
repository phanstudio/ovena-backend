# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone
from django.db import transaction
from payments.models.subscription import Plan, Subscription, Invoice, PlanAudience, Feature, Status
from .serializers import (
    SubscriptionSerializer, InvoiceSerializer, PlanSerializer, PlanCreateSerializer,
    PlanWithFeaturesSerializer, FeatureSerializer, SubscriptionCreateSerializer
)
from payments.integrations.client import client
from admin_api.views import BaseAppAdminAPIView
from rest_framework.generics import (
    ListCreateAPIView, RetrieveUpdateAPIView, 
    RetrieveUpdateDestroyAPIView, CreateAPIView, 
    RetrieveAPIView, ListAPIView, GenericAPIView
)


class CreateSubscriptionView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SubscriptionCreateSerializer

    def get_user_info(self, request):
        return {
            "email": request.user.email,
            # "first_name":request.user.first_name,
            # last_name:request.user.last_name,
        }

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
            customer_resp = client.create_customer( # use get customer profile for the names
                self.get_user_info(request)
            )
            customer_code = customer_resp["data"]["customer_code"]
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
                    "metadata":metadata
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
            data["authorization_url"] = sub_data["authorization_url"],

        # 3. Don't create local subscription yet – wait for webhook.
        return Response(data)


class CancelSubscriptionView(APIView):
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
            client.disable_subscription(sub.paystack_subscription_code)
        except Exception as e:
            # Log error but still deactivate locally
            pass

        sub.active = False
        sub.cancelled_at = timezone.now()
        sub.save(update_fields=["active", "cancelled_at", "updated_at"])

        return Response({"status": "cancelled"})


class CurrentSubscriptionView(APIView):
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


class InvoiceHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        invoices = Invoice.objects.filter(
            subscription__user=request.user
        ).order_by("-created_at")
        serializer = InvoiceSerializer(invoices, many=True)
        return Response(serializer.data)


class ClientPlanListCreateView(ListAPIView):
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


class RetryInvoicePaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, invoice_id):
        try:
            invoice = Invoice.objects.select_related("subscription").get(
                id=invoice_id,
                subscription__user=request.user,
                status=Status.FAILED,
            )
        except Invoice.DoesNotExist:
            return Response({"error": "Invoice not found or not retryable"}, status=404)

        try:
            resp = client.initialize_transaction({
                "email": request.user.email,
                "amount": invoice.amount,
                "invoice_limit": 1,            # one-time charge
                "subscription": invoice.subscription.paystack_subscription_code,
                # this ties the payment back to the subscription
            })
            return Response({"authorization_url": resp["data"]["authorization_url"]})
        except Exception as e:
            return Response({"error": str(e)}, status=500)


class SubscriptionUpdateCardView(APIView):
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