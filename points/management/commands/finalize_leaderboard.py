"""
payments/points/management/commands/finalize_leaderboard.py

Run this once a month, shortly after midnight on the 1st, e.g. via
celery-beat or a plain cron entry:

    5 0 1 * *  python manage.py finalize_leaderboard

It's idempotent -- safe to re-run or retry if the scheduler fires twice.
By default it finalizes *last* month; pass --period to backfill a specific
month (useful if the job didn't run and you need to reconstruct it from
the ledger before those rows are pruned/archived).
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from points import leaderboard_service


class Command(BaseCommand):
    help = "Finalize (freeze) the points leaderboard for a completed month."

    def add_arguments(self, parser):
        parser.add_argument(
            "--period",
            type=str,
            default=None,
            help="Month to finalize, formatted YYYY-MM. Defaults to last month.",
        )

    def handle(self, *args, **options):
        period = None
        if options["period"]:
            try:
                year, month = (int(p) for p in options["period"].split("-"))
                period = date(year, month, 1)
            except ValueError:
                raise CommandError("--period must be formatted YYYY-MM")

        snapshot = leaderboard_service.finalize_leaderboard_for_period(period)
        entry_count = snapshot.entries.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Leaderboard finalized for {snapshot.period_start:%Y-%m} ({entry_count} users)."
            )
        )
