from django.db import models
from .profile import BusinessAdmin

class BusinessOnboardStatus(models.Model):
    PHASE = [(i, day) for i, day in enumerate(
        ["notStarted","phase1", "phase2", "phase3"]
    )]
    admin = models.OneToOneField(BusinessAdmin, on_delete=models.CASCADE, related_name="cerd")
    onboarding_step = models.IntegerField(choices=PHASE, default=0)
    is_onboarding_complete = models.BooleanField(default=False)
