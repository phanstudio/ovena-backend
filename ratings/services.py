from dataclasses import dataclass
from django.db import transaction
from django.db.models import Avg, Count

from .models import DriverRating, BranchRating
# come back

@dataclass(frozen=True)
class RatingStats:
    avg: float
    count: int


class RatingService:
    @staticmethod
    def driver_stats(driver_id: int) -> RatingStats:
        data = DriverRating.objects.for_driver(driver_id).aggregate(
            avg=Avg("stars"),
            count=Count("id"),
        )
        return RatingStats(avg=float(data["avg"] or 0), count=int(data["count"] or 0))

    @staticmethod
    def branch_stats(branch_id: int) -> RatingStats:
        data = BranchRating.objects.for_branch(branch_id).aggregate(
            avg=Avg("stars"),
            count=Count("id"),
        )
        return RatingStats(avg=float(data["avg"] or 0), count=int(data["count"] or 0))

    @staticmethod
    def order_ratings(order_id: int, rater_id: int):
        """
        Useful for "did user already rate this order?" checks.
        """
        driver_rating = DriverRating.objects.filter(order_id=order_id, rater_id=rater_id).first()
        branch_rating = BranchRating.objects.filter(order_id=order_id, rater_id=rater_id).first()
        return {"driver_rating": driver_rating, "branch_rating": branch_rating}

    @staticmethod
    @transaction.atomic
    def submit_for_order(
        *,
        order,
        rater,
        driver_payload: dict | None = None,
        branch_payload: dict | None = None,
    ):
        """
        Submit driver and/or branch rating in one transaction.
        - Safe to call from one endpoint after delivery.
        - Uses update_or_create so user can edit their rating for that order.
        """
        created_or_updated = {}

        if driver_payload is not None:
            obj, _ = DriverRating.objects.update_or_create(
                order=order,
                rater=rater,
                driver=order.driver,
                defaults={
                    "stars": driver_payload["stars"],
                    "review": driver_payload.get("review", ""),
                    "complaint_type": driver_payload.get("complaint_type"),
                },
            )
            # enforce model-level validation
            obj.full_clean()
            obj.save()
            created_or_updated["driver_rating"] = obj

        if branch_payload is not None:
            obj, _ = BranchRating.objects.update_or_create(
                order=order,
                rater=rater,
                branch=order.branch,
                defaults={
                    "stars": branch_payload["stars"],
                    "review": branch_payload.get("review", ""),
                    "complaint_type": branch_payload.get("complaint_type"),
                },
            )
            obj.full_clean()
            obj.save()
            created_or_updated["branch_rating"] = obj

        return created_or_updated
