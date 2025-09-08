from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
import uuid
from addresses.models import Address

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
        ("restaurant", "Restaurant"),
    ], default="customer")

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    # how to swap
    USERNAME_FIELD = "email"   # but you can swap to phone if OTP-only
    REQUIRED_FIELDS = ["name"]

    def __str__(self):
        return self.email or self.phone_number

class CustomerProfile(models.Model): # create a simple view to change the defualt address
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="customer_profile")
    birth_date = models.DateField(null=True, blank=True)
    addresses = models.ManyToManyField(Address, related_name="customers", blank=True)
    default_address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name="default_for_customers")# set normally but change if requested
    referral_code = models.CharField(max_length=20, unique=True, blank=True)
    referred_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals"
    )

    def save(self, *args, **kwargs):
        if not self.referral_code:
            # generate a unique referral code on creation
            self.referral_code = str(uuid.uuid4())[:8].upper()
        super().save(*args, **kwargs)

    @property
    def successful_referrals(self):
        return CustomerProfile.objects.filter(
            referred_by=self,
            user__orders__status="delivered"
        ).distinct().count()

    @property
    def age(self):
        from datetime import date
        if not self.birth_date:
            return None
        today = date.today()
        return today.year - self.birth_date.year - (
            (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
        )

class DriverProfile(models.Model): # does the referral system work with drivers
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="driver_profile")
    nin = models.CharField(max_length=50)
    driver_license = models.CharField(max_length=50)
    plate_number = models.CharField(max_length=20)
    vehicle_type = models.CharField(max_length=50)
    photo = models.ImageField(upload_to="drivers/photos/")

class Restaurant(models.Model): # does the referral system work with resturants
    company_name = models.CharField(max_length=255)
    bn_number = models.CharField(max_length=100)  # business number
    certification = models.FileField(upload_to="restaurants/certs/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.company_name

class Branch(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=255)  # e.g. "Ikeja Branch"
    phone_number = models.CharField(max_length=20, blank=True)
    location = models.ForeignKey(Address, on_delete=models.CASCADE, related_name="branches")

    def __str__(self):
        return f"{self.restaurant.company_name} - {self.name}"

class Employee(models.Model): # change to manager
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="employees")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="employee_roles")

    role = models.CharField(max_length=50, choices=[
        ("manager", "Manager"),
        ("cashier", "Cashier"), # change to desk guy?
    ])

    def __str__(self):
        return f"{self.user.name} - {self.role} @ {self.branch.name}"

class Rating(models.Model):
    rater = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="ratings_given"  # unique related_name
    )
    rated = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="ratings_received"  # unique related_name
    )
    review = models.TextField(blank=True)
    stars = models.PositiveSmallIntegerField()  # 1-5 stars

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("rater", "rated")  # optional: prevent multiple ratings per rater/rated

    def __str__(self):
        return f"{self.rater} → {self.rated}: {self.stars}⭐"

