from django.core.management.base import BaseCommand
from django.db import models

from accounts.models import CustomerProfile, DriverProfile
from menu.models import Order
from ratings.models import DriverRating, BranchRating


class Command(BaseCommand):
    help = "Report standalone profile integrity and foreign key dependents."

    def handle(self, *args, **options):
        total_customers = CustomerProfile.objects.count()
        total_drivers = DriverProfile.objects.count()
        customers_without_user = CustomerProfile.objects.filter(user__isnull=True).count()
        drivers_without_user = DriverProfile.objects.filter(user__isnull=True).count()
        customers_without_code = CustomerProfile.objects.filter(referral_code__isnull=True).count()
        drivers_without_code = DriverProfile.objects.filter(referral_code__isnull=True).count()

        self.stdout.write("Standalone Profile Integrity (ProfileBase MTI Eliminated)")
        self.stdout.write(f"- total customers: {total_customers} (missing user: {customers_without_user}, missing code: {customers_without_code})")
        self.stdout.write(f"- total drivers: {total_drivers} (missing user: {drivers_without_user}, missing code: {drivers_without_code})")

        self.stdout.write("")
        self.stdout.write("FK Dependents (Preserved)")
        self.stdout.write(f"- menu.Order -> orderer(CustomerProfile): {Order.objects.exclude(orderer__isnull=True).count()}")
        self.stdout.write(f"- menu.Order -> driver(DriverProfile): {Order.objects.exclude(driver__isnull=True).count()}")
        self.stdout.write(f"- ratings.DriverRating -> rater(CustomerProfile): {DriverRating.objects.exclude(rater__isnull=True).count()}")
        self.stdout.write(f"- ratings.DriverRating -> driver(DriverProfile): {DriverRating.objects.exclude(driver__isnull=True).count()}")
        self.stdout.write(f"- ratings.BranchRating -> rater(CustomerProfile): {BranchRating.objects.exclude(rater__isnull=True).count()}")

