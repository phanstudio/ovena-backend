from dataclasses import dataclass
from django.db import transaction
from django.db.models import Avg, Count

from .models import DriverRating, BranchRating
from accounts.models import DriverProfile, Branch, Business
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
        created_or_updated = {}

        if driver_payload is not None:
            # Get old rating if exists
            old_rating = DriverRating.objects.filter(
                order=order,
                rater=rater,
            ).values('stars').first()

            obj, created = DriverRating.objects.update_or_create(
                order=order,
                rater=rater,
                driver=order.driver,
                defaults={
                    "stars": driver_payload["stars"],
                    "review": driver_payload.get("review", ""),
                    "complaint_type": driver_payload.get("complaint_type"),
                },
            )
            obj.full_clean()
            obj.save()
            created_or_updated["driver_rating"] = obj

            # Update driver stats incrementally
            driver = order.driver
            if created:
                # New rating
                driver.rating_sum += obj.stars
                driver.rating_count += 1
            else:
                # Updated rating - adjust the difference
                old_stars = old_rating['stars']
                driver.rating_sum += (obj.stars - old_stars)
                # count stays the same
            
            driver.avg_rating = (
                driver.rating_sum / driver.rating_count 
                if driver.rating_count > 0 else 0.0
            )
            driver.save(update_fields=['rating_sum', 'rating_count', 'avg_rating'])

        if branch_payload is not None:
            old_rating = BranchRating.objects.filter(
                order=order,
                rater=rater,
            ).values('stars').first()

            obj, created = BranchRating.objects.update_or_create(
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

            # Update branch stats
            branch = order.branch
            if created:
                branch.rating_sum += obj.stars
                branch.rating_count += 1
            else:
                old_stars = old_rating['stars']
                branch.rating_sum += (obj.stars - old_stars)
            
            branch.avg_rating = (
                branch.rating_sum / branch.rating_count 
                if branch.rating_count > 0 else 0.0
            )
            branch.save(update_fields=['rating_sum', 'rating_count', 'avg_rating'])

            # Update business stats (rollup from all branches)
            if branch.business:
                business = branch.business
                # Recalculate business rating from all its branches
                from django.db.models import Sum
                branch_stats = Branch.objects.filter(
                    business=business
                ).aggregate(
                    total_sum=Sum('rating_sum'),
                    total_count=Sum('rating_count')
                )
                business.rating_sum = branch_stats['total_sum'] or 0
                business.rating_count = branch_stats['total_count'] or 0
                business.avg_rating = (
                    business.rating_sum / business.rating_count 
                    if business.rating_count > 0 else 0.0
                )
                business.save(update_fields=['rating_sum', 'rating_count', 'avg_rating'])

        return created_or_updated
