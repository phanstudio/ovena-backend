from addresses.models import Address
from django.utils import timezone
from authflow.services import generate_referral_code
from django.db import models, IntegrityError, transaction
from .main import User, Branch, Business

# profile
class ProfileBase(models.Model):
    """
    Shared fields + common behaviors for any profile.
    """
    referral_code = models.CharField(max_length=20, unique=True, null=True, blank=True, db_index=True)
    referred_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
    
    def _generate_referral_code(self) -> str:
        return generate_referral_code(8)
    
    # for no collisions
    # base62: 9+
    # base36: 11+
    
    # I might adjust or out rightly add to this, if the error occur no fail state for it
    def _pick_unique_code_batch(self, batch_size=25) -> str:
        # generate candidate codes in memory
        candidates = {self._generate_referral_code() for _ in range(batch_size)}

        # single DB query to find which ones already exist
        taken = set(
            self.__class__.objects
            .filter(referral_code__in=candidates)
            .values_list("referral_code", flat=True)
        )

        # pick a free one
        available = list(candidates - taken)
        if not available:
            raise ValueError("All generated referral codes were taken; increase batch_size or retry.")
        return available[0]

    def save(self, *args, **kwargs):
        if self.referral_code:
            return super().save(*args, **kwargs)

        # try a few rounds
        for _ in range(10):
            self.referral_code = self._pick_unique_code_batch(batch_size=25)
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                # collision still possible under concurrency, so retry
                self.referral_code = None

        raise RuntimeError("Could not generate a unique referral code after multiple attempts.")

class CustomerProfile(ProfileBase): # create a simple view to change the defualt address
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="customer_profile")
    birth_date = models.DateField(null=True, blank=True)
    addresses = models.ManyToManyField(Address, related_name="customers", blank=True)
    default_address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name="default_for_customers")# set normally but change if requested

    # def save(self, *args, **kwargs):
    #     # Generate referral code once (safe against collisions)
    #     if not self.referral_code:
    #         while True:
    #             code = generate_referral_code(8)
    #             if not CustomerProfile.objects.filter(referral_code=code).exists():
    #                 self.referral_code = code
    #                 break
    #     super().save(*args, **kwargs)

    @property
    def age(self):
        if not self.birth_date:
            return None
        today = timezone.localdate()
        return today.year - self.birth_date.year - (
            (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
        )

    @property
    def successful_referrals(self):
        return CustomerProfile.objects.filter(
            referred_by=self,
            user__orders__status="delivered"
        ).distinct().count()

# driver related
class DriverProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='driver_profile')
    
    # Availability
    is_online = models.BooleanField(default=False)
    is_available = models.BooleanField(default=False)  # Online but not on delivery
    current_order = models.ForeignKey('menu.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='current_driver')
    
    # Stats
    total_deliveries = models.IntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=5.0)
    
    # Tracking
    last_location_update = models.DateTimeField(blank=True, null=True)
    
    # Vehicle info
    vehicle_type = models.CharField(max_length=50, blank=True, null=True)  # bike, car, etc.
    vehicle_number = models.CharField(max_length=50, blank=True, null=True)

    rating_sum = models.IntegerField(default=0)          # total stars
    rating_count = models.PositiveIntegerField(default=0)
    avg_rating = models.FloatField(default=0.0, db_index=True)  # optional but convenient
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Driver: {self.user.name}"
    
# for verification, every driver must have cred
class DriverCred(models.Model): # does the referral system work with drivers
    user = models.OneToOneField(DriverProfile, on_delete=models.CASCADE, related_name="driver_profile")
    nin = models.CharField(max_length=50)
    driver_license = models.CharField(max_length=50)
    plate_number = models.CharField(max_length=20)
    vehicle_type = models.CharField(max_length=50)
    photo = models.ImageField(upload_to="drivers/photos/")

class PrimaryAgent(models.Model): # only one primary users, so the branch should be a one to one
    branch = models.OneToOneField(Branch, on_delete=models.CASCADE, related_name="primary_agent")
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.user.name} - vendor agent @ {self.branch.name}"
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["branch"], name="unique_primary_agent_per_branch"
            )
        ]

class LinkedStaff(models.Model):
    created_by = models.ForeignKey(
        PrimaryAgent, on_delete=models.CASCADE, related_name="linked_staff"
    )
    device_name = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.device_name or 'Unnamed Device'} - staff for {self.created_by.user.name}"

class BusinessAdmin(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="business_admin")
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="admin")

    def __str__(self):
        return f"{self.user.name} admin @ {self.business.business_name}"

# admin Profle connected to the restaurant:
# password;
