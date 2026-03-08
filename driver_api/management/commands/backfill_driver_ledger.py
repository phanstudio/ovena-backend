from django.core.management.base import BaseCommand

from driver_api.services import ledger_credit_for_delivered_order
from menu.models import Order


class Command(BaseCommand):
    help = "Backfill driver ledger credit entries from delivered orders."

    def handle(self, *args, **options):
        created = 0
        scanned = 0
        qs = Order.objects.filter(status="delivered", driver__isnull=False).select_related("driver")
        for order in qs.iterator():
            scanned += 1
            entry = ledger_credit_for_delivered_order(order)
            if entry:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Scanned={scanned}, created={created}"))

