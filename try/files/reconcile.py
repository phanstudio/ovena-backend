"""
Management command: reconcile payouts against Paystack (batch + realtime)
Run via: python manage.py reconcile
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from payments.reconciliation.alerts import send_reconciliation_alert
from payments.reconciliation.service import run_reconciliation


class Command(BaseCommand):
    help = "Reconcile payouts against Paystack API"

    def handle(self, *args, **options):
        run_date = date.today() - timedelta(days=1)
        summary = run_reconciliation(run_date=run_date, alert_callback=send_reconciliation_alert)

        if summary["mismatches"]:
            self.stdout.write(
                self.style.ERROR(
                    f"[RECONCILE] {summary['mismatches']} mismatches found (checked={summary['checked']}, log={summary['log_id']})"
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"[RECONCILE] Clean run. checked={summary['checked']} log={summary['log_id']}"))
