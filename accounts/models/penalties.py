from django.db import models
from .main import User
from django.utils import timezone

class Penalty(models.Model):
    ISSUER_SUPPORT = "support"
    ISSUER_SYSTEM = "system"
    ISSUER_CHOICES = [
        (ISSUER_SUPPORT, "Support"),
        (ISSUER_SYSTEM, "System"),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="penalties")
    role = models.CharField(max_length=20, choices=[("driver", "Driver"), ("business_admin", "Business Admin")])
    reason = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)  # so an overturned appeal can soft-void it
    issued_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    issuer_type = models.CharField(max_length=20, choices=ISSUER_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

# we need penalties images and images for deliveries
# when we appeal what happens to the suspenstion???, we need it in the jwt portion.
class Suspension(models.Model):
    LEVEL_CHOICES = [("temporary", "Temporary"), ("permanent", "Permanent")]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="suspensions")
    role = models.CharField(max_length=20, choices=Penalty._meta.get_field("role").choices)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    lifted_at = models.DateTimeField(null=True, blank=True)

class Appeal(models.Model):
    STATUS_CHOICES = [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")]

    suspension = models.OneToOneField(Suspension, on_delete=models.CASCADE, related_name="appeal")
    submitted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    reviewed_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    def approve(self, reviewer):
        self.status = "approved"
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.save()
        self.suspension.lifted_at = timezone.now()
        self.suspension.save()
        # penalty count is untouched on purpose — the strike stands, only the ban is lifted

    def reject(self, reviewer, notes=""):
        self.status = "rejected"
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.resolution_notes = notes
        self.save()
