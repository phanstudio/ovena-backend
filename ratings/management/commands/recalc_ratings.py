from django.core.management.base import BaseCommand
from django.db.models import Avg, Count, Model
from django.db.models.functions import Coalesce
from django.db import transaction

from ratings.models import DriverRating, BranchRating, RatingBase
from accounts.models import DriverProfile, Branch

@transaction.atomic
def refresh_rating_stats(basemode: Model, rating: RatingBase, fk_field: str, batch_size: int = 2000) -> None:
    basemode.objects.update(avg_rating=0.0, rating_count=0)

    driver_stats_qs = (
        rating.objects
        .values(fk_field)
        .annotate(avg=Coalesce(Avg("stars"), 0.0), cnt=Count("id"))
        .iterator()
    )

    buffer = []
    for row in driver_stats_qs:
        buffer.append(
            basemode(
                id=row[fk_field],
                avg_rating=float(row["avg"]),
                rating_count=int(row["cnt"]),
            )
        )
        if len(buffer) >= batch_size:
            basemode.objects.bulk_update(buffer, ["avg_rating", "rating_count"], batch_size=batch_size)
            buffer.clear()

    if buffer:
        basemode.objects.bulk_update(buffer, ["avg_rating", "rating_count"], batch_size=batch_size)

class Command(BaseCommand):
    help = "Recalculate avg_rating and rating_count on drivers and branches."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=3000)

    def handle(self, *args, **options):
        refresh_rating_stats(DriverProfile, DriverRating, "driver_id", batch_size=options["batch_size"])
        refresh_rating_stats(Branch, BranchRating, "branch_id", batch_size=options["batch_size"])
        self.stdout.write(self.style.SUCCESS("Ratings stats recalculated."))


# Run with: python manage.py recalc_ratings