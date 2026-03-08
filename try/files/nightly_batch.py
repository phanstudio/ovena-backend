"""
Management command: nightly batch transfer
Run via: python manage.py nightly_batch
"""
from django.core.management.base import BaseCommand

from payments.payouts.services import execute_batch


class Command(BaseCommand):
    help = "Run nightly batch payout to all pending withdrawal requests"

    def handle(self, *args, **options):
        result = execute_batch()
        self.stdout.write(
            self.style.SUCCESS(
                f"[BATCH] Done. date={result['batch_date']} count={result['count']} queued={result['queued']}"
            )
        )
