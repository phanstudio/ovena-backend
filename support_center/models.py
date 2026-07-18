import os
import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from authflow.services.model import AbstractBaseModel, AbstractUBaseModel

# Keep this in sync with ALLOWED_ATTACHMENT_CONTENT_TYPES in serializers.py
ALLOWED_ATTACHMENT_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "heic"]
MAX_ATTACHMENT_SIZE_BYTES = 5 * 1024 * 1024  # 5MB


def ticket_attachment_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"support_tickets/{instance.message.ticket_id}/{uuid.uuid4().hex}{ext}"

class SupportTicket(AbstractUBaseModel):
    OWNER_DRIVER = "driver"
    OWNER_BUSINESS_ADMIN = "business_admin"
    OWNER_BUSINESS_STAFF = "business_staff"
    OWNER_CUSTOMER = "customer"
    OWNER_CHOICES = [
        (OWNER_DRIVER, "Driver"),
        (OWNER_BUSINESS_ADMIN, "Business Admin"),
        (OWNER_BUSINESS_STAFF, "Business Staff"),
        (OWNER_CUSTOMER, "Customer"),
    ]

    STATUS_OPEN = "open"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RESOLVED = "resolved"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_CLOSED, "Closed"),
    ]

    PRIORITY_LOW = "low"
    PRIORITY_MEDIUM = "medium"
    PRIORITY_HIGH = "high"
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_MEDIUM, "Medium"),
        (PRIORITY_HIGH, "High"),
    ]

    CREATED_BY_USER = "user"
    CREATED_BY_SUPPORT = "support"
    CREATED_BY_SYSTEM = "system"
    CREATED_BY_CHOICES = [
        (CREATED_BY_USER, "User"),
        (CREATED_BY_SUPPORT, "Support"),
        (CREATED_BY_SYSTEM, "System"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_support_tickets",
    )
    owner_role = models.CharField(max_length=20, choices=OWNER_CHOICES)
    category = models.CharField(max_length=80, blank=True, default="general")
    subject = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    is_blocking = models.BooleanField(default=False)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_support_tickets_central",
    )
    
    created_by_type = models.CharField(max_length=20,choices=CREATED_BY_CHOICES,default=CREATED_BY_USER,)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_support_tickets"
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["owner_role", "status", "-created_at"]),
            models.Index(fields=["owner", "status", "-created_at"]),
            models.Index(fields=["is_blocking", "status"]),
        ]

    def __str__(self):
        return f"SupportTicket({self.id}) {self.owner_role} {self.subject}"


class SupportTicketMessage(AbstractBaseModel):
    SENDER_DRIVER = "driver"
    SENDER_BUSINESS_ADMIN = "business_admin"
    SENDER_BUSINESS_STAFF = "business_staff"
    SENDER_CUSTOMER = "customer"
    SENDER_SUPPORT = "support"
    SENDER_SYSTEM = "system"
    SENDER_CHOICES = [
        (SENDER_DRIVER, "Driver"),
        (SENDER_BUSINESS_ADMIN, "Business Admin"),
        (SENDER_BUSINESS_STAFF, "Business Staff"),
        (SENDER_CUSTOMER, "Customer"),
        (SENDER_SUPPORT, "Support"),
        (SENDER_SYSTEM, "System"),
    ]

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    sender_type = models.CharField(max_length=20, choices=SENDER_CHOICES)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    message = models.TextField()

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["ticket", "created_at"])
        ]


class SupportTicketAttachment(AbstractBaseModel):
    message = models.ForeignKey(
        SupportTicketMessage,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    # ImageField validates (via Pillow) that the uploaded file is actually
    # a real image, on top of the extension whitelist below.
    file = models.ImageField(
        upload_to=ticket_attachment_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=ALLOWED_ATTACHMENT_EXTENSIONS)],
    )
    original_filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="support_ticket_attachments",
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["message", "created_at"]),
        ]

    def __str__(self):
        return f"SupportTicketAttachment({self.id}) msg={self.message_id}"
