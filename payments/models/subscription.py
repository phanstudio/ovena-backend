from django.db import models

class BaseSubscition(models.Model):
    # id = 
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class Feature(BaseSubscition):
    code = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)


class Plan(BaseSubscition):
    name = models.CharField(max_length=100)
    paystack_plan_code = models.CharField(max_length=100)
    amount = models.IntegerField()
    interval = models.CharField(max_length=20)

    features = models.ManyToManyField(Feature, blank=True)


class Subscription(BaseSubscition):
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True)

    active = models.BooleanField(default=False)
    next_payment_date = models.DateTimeField(null=True, blank=True)

    def has_feature(self, feature_code: str) -> bool:
        if not self.active or not self.plan:
            return False
        return self.plan.features.filter(code=feature_code).exists()


# models.py

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()

class Plan(models.Model):
    name = models.CharField(max_length=100)
    paystack_plan_code = models.CharField(max_length=100)
    amount = models.IntegerField()  # in kobo
    interval = models.CharField(max_length=20)  # monthly, yearly

class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True)

    paystack_subscription_code = models.CharField(max_length=100, null=True)
    paystack_customer_code = models.CharField(max_length=100, null=True)

    active = models.BooleanField(default=False)
    start_date = models.DateTimeField(null=True)
    next_payment_date = models.DateTimeField(null=True)