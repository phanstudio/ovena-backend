from django.core.management.base import BaseCommand
from django.db import models

from accounts.models import CustomerProfile, DriverProfile
from menu.models import Order
from ratings.models import DriverRating, BranchRating


class Command(BaseCommand):
    help = "Report MTI-cutover readiness for ProfileBase-dependent models."

    def handle(self, *args, **options):
        missing_customer = CustomerProfile.objects.filter(base_profile__isnull=True).count()
        missing_driver = DriverProfile.objects.filter(base_profile__isnull=True).count()
        bad_customer_type = CustomerProfile.objects.exclude(base_profile__profile_type="customer").count()
        bad_driver_type = DriverProfile.objects.exclude(base_profile__profile_type="driver").count()
        bad_customer_user = CustomerProfile.objects.exclude(base_profile__user_id=models.F("user_id")).count()
        bad_driver_user = DriverProfile.objects.exclude(base_profile__user_id=models.F("user_id")).count()

        self.stdout.write("ProfileBase Link Integrity")
        self.stdout.write(f"- customer missing base_profile: {missing_customer}")
        self.stdout.write(f"- driver missing base_profile: {missing_driver}")
        self.stdout.write(f"- customer wrong profile_type: {bad_customer_type}")
        self.stdout.write(f"- driver wrong profile_type: {bad_driver_type}")
        self.stdout.write(f"- customer base_profile user mismatch: {bad_customer_user}")
        self.stdout.write(f"- driver base_profile user mismatch: {bad_driver_user}")

        self.stdout.write("")
        self.stdout.write("FK Dependents (high-impact)")
        self.stdout.write(f"- menu.Order -> orderer(CustomerProfile): {Order.objects.exclude(orderer__isnull=True).count()}")
        self.stdout.write(f"- menu.Order -> driver(DriverProfile): {Order.objects.exclude(driver__isnull=True).count()}")
        self.stdout.write(f"- ratings.DriverRating -> rater(CustomerProfile): {DriverRating.objects.exclude(rater__isnull=True).count()}")
        self.stdout.write(f"- ratings.DriverRating -> driver(DriverProfile): {DriverRating.objects.exclude(driver__isnull=True).count()}")
        self.stdout.write(f"- ratings.BranchRating -> rater(CustomerProfile): {BranchRating.objects.exclude(rater__isnull=True).count()}")
