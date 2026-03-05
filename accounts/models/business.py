from django.db import models
from .profile import BusinessAdmin
from .main import Business
from authflow.storage_backends import PrivateStorage

class BusinessOnboardStatus(models.Model):
    PHASE = [(i, day) for i, day in enumerate(
        ["notStarted","phase1", "phase2", "phase3"]
    )]
    admin = models.OneToOneField(BusinessAdmin, on_delete=models.CASCADE, related_name="cerd")
    onboarding_step = models.IntegerField(choices=PHASE, default=0)
    is_onboarding_complete = models.BooleanField(default=False)


class BusinessCerd(models.Model):
    BUSINESS_TYPE_CHOICES = [
        ("LLC", "Limited Liability Company"),
        ("C", "Corporations"),
        ("P", "Partnerships "),
        ("SP", "Sole Proprietorships"),
    ]

    class DocType(models.TextChoices):
        CAC = "cac", "CAC Document"
        TAX = "tax", "Tax Document"
        ID = "id", "ID Document"
        OTHER = "other", "Other"
    
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="cerd")
    business_type = models.CharField(max_length=120, choices=BUSINESS_TYPE_CHOICES, default="restaurant")
    doc_type = models.CharField(max_length=20, choices=DocType.choices, default=DocType.OTHER)
    business_doc = models.FileField(
        upload_to="business/docs/",
        storage=PrivateStorage(),  # private bucket
        blank=True,
        null=True
    )

    # KYC / registration (optional at initial step)
    registered_business_name = models.CharField(max_length=255, null=True, blank=True) # well also remove to another model
    tax_identification_number = models.CharField(max_length=100, null=True, blank=True) # should be the last 4 bdigits for safety
    rc_number = models.CharField(max_length=100, null=True, blank=True)
    bn_number = models.CharField(max_length=100, blank=True, default="")

    def __str__(self):
        return self.registered_business_name

class BusinessPayoutAccount(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="payout")

    bank_name = models.CharField(max_length=120)
    account_number = models.CharField(max_length=30)
    account_name = models.CharField(max_length=120)

    # Safer than storing BVN raw:
    # bvn_last4 = models.CharField(max_length=4, null=True, blank=True)
    bvn = models.CharField(max_length=4, null=True, blank=True)
    bvn_verification_ref = models.CharField(max_length=120, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
