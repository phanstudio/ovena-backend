from django.db import models
from django.contrib.auth import get_user_model
from common.models.ulid import ULIDField
from django.core.validators import MinValueValidator

User = get_user_model()

class PlanAudience(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    BUSINESS = "business", "Business"
    NOONE = "none", "None"


class BillingInterval(models.TextChoices):
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"
    YEARLY = "yearly", "Yearly"


class Status(models.TextChoices):
    PENDING = "pending", "Pending"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    REVERSED = "reversed", "Reversed"


class BaseSubscription(models.Model):
    # id = 
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Feature(BaseSubscription):
    code = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.code


class Plan(BaseSubscription):
    audience = models.CharField(
        max_length=20,
        choices=PlanAudience.choices,
        db_index=True,
    )
    name = models.CharField(max_length=100)
    paystack_plan_code = models.CharField(max_length=100)
    amount = models.BigIntegerField(validators=[MinValueValidator(0)])  # stored in lowest denomination (e.g. kobo)
    interval = models.CharField(
        max_length=20,
        choices=BillingInterval.choices,
        default=BillingInterval.MONTHLY,
    )
    features = models.ManyToManyField(Feature, blank=True, related_name="plans")
    description = models.TextField(default="")

    def __str__(self):
        return f"{self.name} ({self.get_audience_display()}, {self.get_interval_display()})"


class Subscription(BaseSubscription):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, related_name="subscriptions")
    paystack_subscription_code = models.CharField(max_length=100, null=True, unique=True)
    paystack_customer_code = models.CharField(max_length=100, null=True, unique=True)
    active = models.BooleanField(default=False)
    start_date = models.DateTimeField(null=True)
    next_payment_date = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(active=True),
                name="unique_active_subscription_per_user",
            )
        ]

    def has_feature(self, feature_code: str) -> bool:
        if not self.active or not self.plan:
            return False
        return self.plan.features.filter(code=feature_code).exists()

    def __str__(self):
        return f"Subscription({self.user_id}, active={self.active})"


class Invoice(BaseSubscription):
    id = ULIDField(primary_key=True)
    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="invoices"
    )
    paystack_invoice_code = models.CharField(max_length=100, unique=True)
    amount = models.BigIntegerField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    failure_reason = models.CharField(max_length=255, blank=True)
    due_date = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Invoice({self.id}, {self.status})"
