# notifications/models.py

from django.conf import settings
from django.db import models


class Notification(models.Model):

    TYPE_GENERIC = "generic"
    TYPE_ORDER = "order"
    TYPE_EARNING = "earning"
    TYPE_WITHDRAWAL = "withdrawal"
    TYPE_SUPPORT = "support"
    TYPE_SYSTEM = "system"

    TYPE_CHOICES = [
        (TYPE_GENERIC, "Generic"),
        (TYPE_ORDER, "Order"),
        (TYPE_EARNING, "Earning"),
        (TYPE_WITHDRAWAL, "Withdrawal"),
        (TYPE_SUPPORT, "Support"),
        (TYPE_SYSTEM, "System"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    notification_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_GENERIC
    )

    title = models.CharField(max_length=160)
    body = models.TextField()

    payload_json = models.JSONField(default=dict, blank=True)

    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.title}"