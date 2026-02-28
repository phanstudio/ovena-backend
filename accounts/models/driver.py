from django.db import models
from .main import User
from django.conf import settings

# driver related
class DriverProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='driver_profile')
    
    # Personal info
    birth_date = models.DateField(null=True, blank=True) # should this be moveed to creds
    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    gender = models.CharField(
        max_length=20,
        choices=[("male","Male"),("female","Female"),("other","Other"),("na","Prefer not to say")],
        default="na"
    )
    residential_address = models.TextField(blank=True) # same as this
    
    # Availability
    is_online = models.BooleanField(default=False)
    is_available = models.BooleanField(default=False)  # Online but not on delivery
    current_order = models.ForeignKey('menu.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='current_driver')
    
    
    # Tracking
    last_location_update = models.DateTimeField(blank=True, null=True)
    
    # Vehicle info
    vehicle_make = models.CharField(max_length=60, blank=True)
    vehicle_type = models.CharField(max_length=50, blank=True, null=True,
        # choices=[("bike","Bike"),("car","Car"),("van","Van")],
    )  # bike, car, etc.
    vehicle_number = models.CharField(max_length=50, blank=True, null=True)

    # Stats
    total_deliveries = models.IntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=5.0) # might remove
    rating_sum = models.IntegerField(default=0)          # total stars
    rating_count = models.PositiveIntegerField(default=0)
    avg_rating = models.FloatField(default=0.0, db_index=True)  # optional but convenient
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Driver: {self.full_name or (self.user.email or self.user.phone_number)}"

    @property
    def full_name(self):
        return (self.first_name + " " + self.last_name).strip()
    
# for verification, every driver must have cred
class DriverCred(models.Model): # does the referral system work with drivers
    user = models.OneToOneField(DriverProfile, on_delete=models.CASCADE, related_name="driver_creds")

    nin_last4 = models.CharField(max_length=4, blank=True)
    bvn_last4 = models.CharField(max_length=4, blank=True)

    # next of kin
    next_of_kin_name = models.CharField(max_length=160, blank=True)
    next_of_kin_phone = models.CharField(max_length=18, blank=True)#, validators=[PHONE_VALIDATOR])

    # Guarantors
    guarantor1_name = models.CharField(max_length=160, blank=True)
    guarantor1_phone = models.CharField(max_length=18, blank=True)#, validators=[PHONE_VALIDATOR])

    guarantor2_name = models.CharField(max_length=160, blank=True)
    guarantor2_phone = models.CharField(max_length=18, blank=True)#, validators=[PHONE_VALIDATOR])

class DriverAvailability(models.Model):
    # Time block bit flags
    MORNING = 1        # 0001
    AFTERNOON = 2      # 0010
    EVENING = 4        # 0100
    LATE_NIGHT = 8     # 1000

    WEEKDAY_CHOICES = [
        (0, "Mon"), (1, "Tue"), (2, "Wed"), (3, "Thu"),
        (4, "Fri"), (5, "Sat"), (6, "Sun"),
    ]

    driver = models.ForeignKey("accounts.DriverProfile", on_delete=models.CASCADE, related_name="availability")
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES)
    time_mask = models.PositiveSmallIntegerField(default=0)  # sum of flags

    class Meta:
        unique_together = [("driver", "weekday")]

    def has(self, flag: int) -> bool:
        return bool(self.time_mask & flag)

class DriverOnboardingSubmission(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    driver = models.ForeignKey("accounts.DriverProfile", on_delete=models.CASCADE, related_name="onboarding_submissions")

    form_version = models.CharField(max_length=20, default="v1")
    answers = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_driver_onboardings"
    )
    reviewer_note = models.TextField(blank=True)

    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class DriverDocument(models.Model): # we can use 
    DOC_DELIVERY_BAG = "delivery_bag"
    DOC_PROFILE_PIC = "profile_pic"
    DOC_SELFIE = "selfie"

    DOC_TYPES = [
        (DOC_DELIVERY_BAG, "Delivery Bag Photo"),
        (DOC_PROFILE_PIC, "Profile Picture"),
        (DOC_SELFIE, "Selfie Verification"),
    ]

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    driver = models.ForeignKey("accounts.DriverProfile", on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=40, choices=DOC_TYPES)
    file = models.ImageField(upload_to="drivers/docs/%Y/%m/")  # ImageField if you want
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewer_note = models.TextField(blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["driver", "doc_type", "status"])]
        constraints = [
            models.UniqueConstraint(fields=["driver", "doc_type"], name="uniq_driver_doc_type")
        ]

class DriverVerification(models.Model):
    TYPE_NIN = "nin"
    TYPE_BVN = "bvn"
    TYPE_CHOICES = [(TYPE_NIN, "NIN"), (TYPE_BVN, "BVN")]

    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [(STATUS_PENDING, "Pending"), (STATUS_SUCCESS, "Success"), (STATUS_FAILED, "Failed")]

    driver = models.ForeignKey("accounts.DriverProfile", on_delete=models.CASCADE, related_name="verifications")
    verification_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)

    provider_name = models.CharField(max_length=60, blank=True)
    provider_ref = models.CharField(max_length=120, blank=True)

    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["driver", "verification_type"], name="uniq_driver_verification_type")
        ]

class DriverBankAccount(models.Model): # should next of kin be used here
    driver = models.OneToOneField(DriverProfile, on_delete=models.CASCADE, related_name="bank_account")

    bank_code = models.CharField(max_length=20, blank=True)   # from API
    bank_name = models.CharField(max_length=120, blank=True)  # cached display name
    account_number = models.CharField(max_length=20, blank=True)
    account_name = models.CharField(max_length=160, blank=True)

    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)


# from django.core.validators import RegexValidator

# PHONE_VALIDATOR = RegexValidator(
#     regex=r"^\+?\d{7,18}$",
#     message="Phone number must be digits, optionally starting with +, 7-18 chars."
# )
