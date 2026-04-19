from django.db import models
from accounts.models import User

class AppAdmin(models.Model):

    class Role(models.TextChoices):
        SUPPORT = "support", "Support Agent"
        SUPERVISOR = "supervisor", "Supervisor"
        FINANCE = "finance", "Finance"
        ADMIN = "admin", "Admin"

    name = models.CharField(max_length=100)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="app_admin"
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.SUPPORT
    )

# class AppSettings(models.Model):
#     name = models.CharField()
#     ...
