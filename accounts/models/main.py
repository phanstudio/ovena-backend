from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.contrib.gis.db import models as gis_models
from django.db import models
from authflow.storage_backends import PrivateStorage

# if what we are check gets big i'm thing of having a separte model for cert inke in driver but only if it gets out of hand
# and a main branch option, on creation of jwt for the resturant create add it to the token
# one database request ediable items, etc?
class Business(models.Model):
    BUSINESS_TYPE_CHOICES = [
        ("restaurant", "Restaurant"),
        ("hotel", "Hotel"),
        ("other", "Other"),
    ]

    business_name = models.CharField(max_length=255)
    business_type = models.CharField(max_length=120, choices=BUSINESS_TYPE_CHOICES, default="restaurant")
    country = models.CharField(max_length=2, blank=True, default="")
    business_address = models.CharField(max_length=500, blank=True, default="")

    email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, default="")
    business_image = models.ImageField(upload_to="business/images/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    onboarding_complete = models.BooleanField(default=False)

    def __str__(self):
        return self.business_name

    @property
    def company_name(self):
        return self.business_name

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

# recheck if indexing is possible on foreign keys and checking can work?
# this branch is not connected to any restorant why
class Branch(gis_models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="branches", null=True, blank=True)
    name = models.CharField(max_length=200)
    
    # Location (GIS)
    address = models.CharField(max_length=500, default="")
    location = gis_models.PointField(geography=True, srid=4326, null=True, blank=True)
    # phone_number = models.CharField(max_length=20, blank=True) 
    # # either here or in the primary agent. or we use the primary agents number to assign into it
    
    # Operational status
    is_active = models.BooleanField(default=True)
    is_accepting_orders = models.BooleanField(default=True)
    
    # Kitchen timing
    average_prep_time = models.IntegerField(default=30, help_text="Minutes")
    
    created_at = models.DateTimeField(auto_now_add=True)

    rating_sum = models.IntegerField(default=0)          # total stars
    rating_count = models.PositiveIntegerField(default=0)
    avg_rating = models.FloatField(default=0.0, db_index=True)  # optional but convenient

    # new
    delivery_method = models.CharField(
        max_length=20,
        choices=[("instant", "Instant"), ("scheduled", "Scheduled")],
        default="instant"
    )
    pre_order_open_period = models.TimeField(null=True, blank=True)
    final_order_time = models.TimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            gis_models.Index(fields=['location']),
        ]
    
    def __str__(self):
        return self.name

    @property
    def restaurant(self):
        return self.business

    @restaurant.setter
    def restaurant(self, value):
        self.business = value

class BranchOperatingHours(models.Model):
    DAYS = [(i, day) for i, day in enumerate(
        ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    )]
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="operating_hours")
    day = models.IntegerField(choices=DAYS)
    open_time = models.TimeField()
    close_time = models.TimeField()
    is_closed = models.BooleanField(default=False)

    class Meta:
        unique_together = ("branch", "day")

# Temporary compatibility alias while code and migrations finish moving to Business.
Restaurant = Business

class UserManager(BaseUserManager):
    def create_user(self, email=None, phone_number=None, password=None, **extra_fields):
        if not email and not phone_number:
            raise ValueError("User must have either an email or phone number")

        if email:
            email = self.normalize_email(email)
            extra_fields["email"] = email

        user = self.model(phone_number=phone_number, **extra_fields)

        if user.is_staff or user.is_superuser:
            if not password:
                raise ValueError("Admins must have a password")
            user.set_password(password)
        else:
            user.set_unusable_password()  # OTP-based login

        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email=email, password=password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, null=True, blank=True)
    phone_number = models.CharField(max_length=18,  null=True, blank=True) #unique=True,
    name = models.CharField(max_length=150, blank=True, null= True)

    role = models.CharField(max_length=20, choices=[
        ("customer", "Customer"),
        ("driver", "Driver"),
        ("buisnessstaff", "BuisnessStaff"), # will be changed to buisness staff
        ("businessadmin", "BusinessAdmin"),
    ], default="customer")

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    # how to swap
    USERNAME_FIELD = "email"   # but you can swap to phone if OTP-only
    REQUIRED_FIELDS = ["name"]

    def __str__(self):
        return self.email or self.phone_number
