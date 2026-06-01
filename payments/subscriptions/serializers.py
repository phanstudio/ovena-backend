from rest_framework import serializers
from payments.models.subscription import Plan, Subscription, Invoice, Feature

class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "name", "amount", "interval", "audience", "description"]

class PlanCreateSerializer(PlanSerializer):

    class Meta(PlanSerializer.Meta):
        fields = PlanSerializer.Meta.fields + ["features"]

class FeatureListSerializer(serializers.ListSerializer):
    def create(self, validated_data):
        features = [
            Feature(**item)
            for item in validated_data
        ]
        return Feature.objects.bulk_create(features)

class FeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        list_serializer_class = FeatureListSerializer
        fields = ['id', 'code', 'description', 'created_at', 'updated_at']

class PlanWithFeaturesSerializer(PlanSerializer):
    features = FeatureSerializer(many=True, read_only=True)

    class Meta(PlanSerializer.Meta):
        fields = PlanSerializer.Meta.fields + ["features"]

class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = ["id", "plan", "active", "start_date", "next_payment_date", "cancelled_at"]

class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ["id", "amount", "status", "due_date", "paid_at"]

class SubscriptionCreateSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField()