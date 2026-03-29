from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.contrib.gis.db import models as gis_models
from django.db import models
from accounts.services.roles import get_user_roles, has_role_all as role_checker

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
    # business_logo = models.ImageField(upload_to="business/logos/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    onboarding_complete = models.BooleanField(default=False) # if this is not true then the resturant doesn't get shown

    def __str__(self):
        return self.business_name

    @property
    def company_name(self):
        return self.business_name

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
    # username = models.CharField(max_length=150, blank=True, null= True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    # how to swap
    USERNAME_FIELD = "email"   # but you can swap to phone if OTP-only
    REQUIRED_FIELDS = ["name"]

    def __str__(self):
        return self.email or self.phone_number

    @property
    def derived_roles(self):
        return get_user_roles(self)

    def has_role(self, role: str) -> bool:
        return role_checker(self, role)

    @property
    def customer_profile(self):
        base = self.get_profile_base(profile_type="customer")
        return getattr(base, "customer_profile", None)

    @property
    def driver_profile(self):
        base = self.get_profile_base(profile_type="driver")
        return getattr(base, "driver_profile", None)
    
    def get_profile_base(self, profile_type):
        # self.profile_bases.filter(profile_type=profile_type).first()
        return self.profile_bases.filter(profile_type=profile_type).select_related().first()
