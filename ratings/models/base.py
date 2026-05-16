from django.db import models
# from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Avg, Count


class RatingBase(models.Model):
    """
    Shared fields + common behaviors for any rating.
    """
    rater = models.ForeignKey(
        "accounts.CustomerProfile",
        on_delete=models.CASCADE,
        related_name="%(class)s_given",
    )

    order = models.ForeignKey(
        "menu.Order",
        on_delete=models.CASCADE,
        related_name="%(class)s_set",
        help_text="The order this rating belongs to (per-order experience).",
    )

    stars = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    review = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["order", "created_at"]),
        ]


class DriverComplaintType(models.TextChoices):
    LATE_DELIVERY = "LATE_DELIVERY", "Late delivery"
    RUDE_DRIVER = "RUDE_DRIVER", "Rude driver"
    UNSAFE_DRIVING = "UNSAFE_DRIVING", "Unsafe driving"
    WRONG_ADDRESS = "WRONG_ADDRESS", "Went to wrong address"
    OTHER = "OTHER", "Other"


class BranchComplaintType(models.TextChoices):
    COLD_FOOD = "COLD_FOOD", "Cold food"
    DIRTY_ENVIRONMENT = "DIRTY_ENVIRONMENT", "Unhygienic/dirty environment"
    WRONG_ORDER = "WRONG_ORDER", "Wrong order"
    DELAYED_PREPARATION = "DELAYED_PREPARATION", "Slow service / delayed preparation"
    RUDE_STAFF = "RUDE_STAFF", "Rude staff"
    OTHER = "OTHER", "Other"


class DriverRatingQuerySet(models.QuerySet):
    def for_driver(self, driver_id: int):
        return self.filter(driver_id=driver_id)

    def stats(self):
        # returns a dict (avg, count)
        agg = self.aggregate(avg=Avg("stars"), count=Count("id"))
        # normalize avg to float or 0
        avg = agg["avg"] or 0
        return {"avg": float(avg), "count": int(agg["count"] or 0)}


class BranchRatingQuerySet(models.QuerySet):
    def for_branch(self, branch_id: int):
        return self.filter(branch_id=branch_id)

    def stats(self):
        agg = self.aggregate(avg=Avg("stars"), count=Count("id"))
        avg = agg["avg"] or 0
        return {"avg": float(avg), "count": int(agg["count"] or 0)}


class DriverRating(RatingBase):
    """
    A rating about the driver, tied to a specific order.
    """
    driver = models.ForeignKey(
        "accounts.DriverProfile",
        on_delete=models.CASCADE,
        related_name="ratings_received",
    )

    complaint_type = models.CharField(
        max_length=40,
        choices=DriverComplaintType.choices,
        blank=True,
        null=True,
        help_text="Select a driver-related complaint reason if applicable.",
    )

    objects = DriverRatingQuerySet.as_manager()

    class Meta(RatingBase.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["order", "rater", "driver"],
                name="unique_driver_rating_per_order",
            ),
        ]
        indexes = RatingBase.Meta.indexes + [
            models.Index(fields=["driver", "created_at"]),
            models.Index(fields=["driver", "stars"]),
        ]
    
    def clean(self):
        super().clean()
        if self.pk:
            old = type(self).objects.filter(pk=self.pk).values("driver_id", "order_id").first()
            if old and (old["driver_id"] != self.driver_id or old["order_id"] != self.order_id):
                raise ValidationError("Cannot change driver/order for an existing rating.")


    def __str__(self):
        return f"{self.rater_id} → driver {self.driver_id}: {self.stars}⭐"


class BranchRating(RatingBase):
    """
    A rating about the branch, tied to a specific order.
    """
    branch = models.ForeignKey(
        "accounts.Branch",
        on_delete=models.CASCADE,
        related_name="ratings_received",
    )

    complaint_type = models.CharField(
        max_length=40,
        choices=BranchComplaintType.choices,
        blank=True,
        null=True,
        help_text="Select a branch-related complaint reason if applicable.",
    )

    objects = BranchRatingQuerySet.as_manager()

    class Meta(RatingBase.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["order", "rater", "branch"],
                name="unique_branch_rating_per_order",
            ),
        ]
        indexes = RatingBase.Meta.indexes + [
            models.Index(fields=["branch", "created_at"]),
            models.Index(fields=["branch", "stars"]),
        ]
    
    def clean(self):
        super().clean()
        if self.pk:
            old = type(self).objects.filter(pk=self.pk).values("branch_id", "order_id").first()
            if old and (old["branch_id"] != self.branch_id or old["order_id"] != self.order_id):
                raise ValidationError("Cannot change branch/order for an existing rating.")

    def __str__(self):
        return f"{self.rater_id} → branch {self.branch_id}: {self.stars}⭐"
