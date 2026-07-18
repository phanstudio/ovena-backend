from rest_framework import serializers

from driver_api.models import SupportFAQCategory, SupportFAQItem
from support_center.models import (
    SupportTicket,
    SupportTicketMessage,
    SupportTicketAttachment,
    MAX_ATTACHMENT_SIZE_BYTES,
)
from django.contrib.auth import get_user_model

User = get_user_model()

# Keep this in sync with ALLOWED_ATTACHMENT_EXTENSIONS in models.py
ALLOWED_ATTACHMENT_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
}
MAX_ATTACHMENTS_PER_MESSAGE = 5

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
    owner_email = serializers.EmailField(
        source="owner.email",
        read_only=True
    )
    owner_id = serializers.CharField(
        source="owner.id",
        read_only=True
    )

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
            "owner_role",
            "owner_id",
            "owner_email",
        ]


class AttachmentValidationMixin:
    """Shared image-attachment validation for ticket/message create serializers."""

    def validate_attachments(self, files):
        if len(files) > MAX_ATTACHMENTS_PER_MESSAGE:
            raise serializers.ValidationError(
                f"You can attach at most {MAX_ATTACHMENTS_PER_MESSAGE} images."
            )

        for f in files:
            if f.content_type not in ALLOWED_ATTACHMENT_CONTENT_TYPES:
                raise serializers.ValidationError(
                    f"'{f.name}' is not a supported image type. Allowed: jpg, png, webp, heic."
                )
            if f.size > MAX_ATTACHMENT_SIZE_BYTES:
                raise serializers.ValidationError(
                    f"'{f.name}' is too large. Max size is {MAX_ATTACHMENT_SIZE_BYTES // (1024 * 1024)}MB."
                )

        return files


class TicketCreateSerializer(AttachmentValidationMixin, serializers.ModelSerializer):
    # Optional images attached to the ticket at creation time. These end up
    # on the auto-created first message, same as attachments on a reply.
    attachments = serializers.ListField(
        child=serializers.ImageField(),
        required=False,
        default=list,
    )

    class Meta:
        model = SupportTicket
        fields = ["category", "subject", "description", "priority", "attachments"]


class TicketDetailSerializer(serializers.ModelSerializer):
    owner_email = serializers.CharField(
        source="owner.email",
        read_only=True
    )
    owner_id = serializers.CharField(
        source="owner.id",
        read_only=True
    )
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
            "owner_role",
            "owner_id",
            "owner_email",
        ]


class SupportTicketAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicketAttachment
        fields = ["id", "file", "original_filename", "content_type", "file_size", "created_at"]
        read_only_fields = fields


class TicketMessageSerializer(serializers.ModelSerializer):
    attachments = SupportTicketAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = SupportTicketMessage
        fields = [
            "id",
            "sender_type",
            "sender_id",
            "message",
            "attachments",
            "created_at",
        ]


class TicketMessageCreateSerializer(AttachmentValidationMixin, serializers.Serializer):
    message = serializers.CharField()
    # New field: real file uploads (multipart/form-data), images only.
    attachments = serializers.ListField(
        child=serializers.ImageField(),
        required=False,
        default=list,
    )


class BusinessTicketListSerializer(TicketListSerializer):
    pass


class BusinessTicketCreateSerializer(TicketCreateSerializer):
    pass


class BusinessTicketDetailSerializer(TicketDetailSerializer):
    pass


class BusinessTicketMessageSerializer(TicketMessageSerializer):
    pass


class BusinessTicketMessageCreateSerializer(TicketMessageCreateSerializer):
    pass


class AppAdminTicketCreateSerializer(TicketCreateSerializer):
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source="owner"   # maps directly to SupportTicket.owner
    )

    role = serializers.ChoiceField(
        choices=SupportTicket.OWNER_CHOICES
    )
