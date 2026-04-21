from addresses.models import Address
from django.utils import timezone
from django.contrib.auth.hashers import check_password, make_password
from authflow.services import generate_referral_code
from django.db import models, IntegrityError, transaction
from .main import User, Branch, Business


# profile
class ProfileBase(models.Model):
    """
    Shared referral identity for any profile type.
    """

    PROFILE_CUSTOMER = "customer"
    PROFILE_DRIVER = "driver"
    PROFILE_TYPE_CHOICES = [
        (PROFILE_CUSTOMER, "Customer"),
        (PROFILE_DRIVER, "Driver"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="profile_bases"
    )
    profile_type = models.CharField(
        max_length=20, choices=PROFILE_TYPE_CHOICES, db_index=True
    )
    referral_code = models.CharField(
        max_length=20, unique=True, null=True, blank=True, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id}:{self.profile_type}"

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
            self.__class__.objects.filter(referral_code__in=candidates).values_list(
                "referral_code", flat=True
            )
        )

        # pick a free one
        available = list(candidates - taken)
        if not available:
            raise ValueError(
                "All generated referral codes were taken; increase batch_size or retry."
            )
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

        raise RuntimeError(
            "Could not generate a unique referral code after multiple attempts."
        )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "profile_type"],
                name="uniq_profilebase_user_type",
            )
        ]


class CustomerProfile(
    ProfileBase
):  # create a simple view to change the defualt address
    profilebase_ptr = models.OneToOneField(
        ProfileBase,
        on_delete=models.CASCADE,
        parent_link=True,
        related_name="customer_profile",
    )
    birth_date = models.DateField(null=True, blank=True)
    addresses = models.ManyToManyField(Address, related_name="customers", blank=True)
    default_address = models.ForeignKey(
        Address,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_customers",
    )  # set normally but change if requested

    def save(self, *args, **kwargs):
        if not self.pk:
            self.profile_type = ProfileBase.PROFILE_CUSTOMER
        else:
            if self.profile_type != ProfileBase.PROFILE_CUSTOMER:
                raise ValueError("Cannot change profile_type on CustomerProfile")
        # print(self.profile_type)
        super().save(*args, **kwargs)

    @property
    def age(self):
        if not self.birth_date:
            return None
        today = timezone.localdate()
        return (
            today.year
            - self.birth_date.year
            - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        )

    @property
    def successful_referrals(self):
        return 0


class BusinessAdmin(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="business_admin"
    )
    business = models.OneToOneField(
        Business, on_delete=models.CASCADE, related_name="admin", null=True, blank=True
    )
    transaction_pin_hash = models.CharField(max_length=128, blank=True, default="")
    # we can change to null later else might be an issue

    def __str__(self):
        return f"{self.user.name} admin @ {self.business.business_name}"

    @property
    def has_transaction_pin(self) -> bool:
        return bool(self.transaction_pin_hash)

    def set_transaction_pin(self, raw_pin: str) -> None:
        self.transaction_pin_hash = make_password(raw_pin)

    def check_transaction_pin(self, raw_pin: str) -> bool:
        if not self.transaction_pin_hash:
            return False
        return check_password(raw_pin, self.transaction_pin_hash)


class PrimaryAgent(
    models.Model
):  # only one primary users, so the branch should be a one to one
    branch = models.OneToOneField(
        Branch,
        on_delete=models.CASCADE,
        related_name="primary_agent",  # i can change this to vengor
    )
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="primary_agent"
    )
    created_by = models.ForeignKey(
        BusinessAdmin,
        on_delete=models.CASCADE,
        related_name="linked_staff",
    )
    device_name = models.CharField(max_length=200)
    revoked = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.name} - vendor agent @ {self.branch.name}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["branch"], name="unique_primary_agent_per_branch"
            ),
            models.UniqueConstraint(
                fields=["device_name"],
                condition=models.Q(revoked=False),
                name="unique_active_device",
            ),
        ]


# admin Profle connected to the restaurant:
# password;
