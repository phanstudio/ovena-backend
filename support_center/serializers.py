from rest_framework import serializers

from driver_api.models import SupportFAQCategory, SupportFAQItem, SupportTicket, SupportTicketMessage


class FAQCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportFAQCategory
        fields = ["id", "name", "sort_order"]


class FAQItemSerializer(serializers.ModelSerializer):
    category = FAQCategorySerializer()

    class Meta:
        model = SupportFAQItem
        fields = ["id", "question", "answer", "tags", "sort_order", "category"]


class TicketListSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = [
            "id",
            "category",
            "subject",
            "status",
            "priority",
            "is_blocking",
            "created_at",
            "closed_at",
        ]


class TicketCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = ["category", "subject", "description", "priority"]


class TicketDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = [
            "id",
            "category",
            "subject",
            "description",
            "status",
            "priority",
            "is_blocking",
            "created_at",
            "updated_at",
            "closed_at",
        ]


class TicketMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicketMessage
        fields = ["id", "sender_type", "sender_id", "message", "attachments_json", "created_at"]


class TicketMessageCreateSerializer(serializers.Serializer):
    message = serializers.CharField()
    attachments_json = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )

