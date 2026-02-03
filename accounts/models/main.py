from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.contrib.gis.db import models as gis_models
from django.utils import timezone
from django.db import models
# if what we are check gets big i'm thing of having a separte model for cert inke in driver but only if it gets out of hand
# and a main branch option, on creation of jwt for the resturant create add it to the token
# one database request ediable items, etc?
class Restaurant(models.Model): # does the referral system work with resturants
    company_name = models.CharField(max_length=255)
    bn_number = models.CharField(max_length=100)  # business number
    certification = models.FileField(upload_to="restaurants/certs/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.company_name

# recheck if indexing is possible on foreign keys and checking can work?
# this branch is not connected to any restorant why
class Branch(gis_models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="branches")
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
    
    class Meta:
        indexes = [
            gis_models.Index(fields=['location']),
        ]
    
    def __str__(self):
        return self.name
#     def __str__(self):
#         return f"{self.restaurant.company_name} - {self.name}"

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
        ("restaurantstaff", "RestaurantStaff"),
    ], default="customer")

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    # how to swap
    USERNAME_FIELD = "email"   # but you can swap to phone if OTP-only
    REQUIRED_FIELDS = ["name"]

    def __str__(self):
        return self.email or self.phone_number
