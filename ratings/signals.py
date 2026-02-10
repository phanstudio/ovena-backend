from django.db import transaction
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from .models import DriverRating, BranchRating

# for batching i might remove signals
# why this select_for_update

def _recompute_avg(sum_val: int, count_val: int) -> float:
    return round(sum_val / count_val, 4) if count_val > 0 else 0.0


@receiver(pre_save, sender=DriverRating)
def driver_rating_pre_save(sender, instance: DriverRating, **kwargs):
    """
    Attach old stars so post_save can update by delta (no queries in post_save except this one).
    """
    if not instance.pk:
        instance._old_stars = None
        return

    old = DriverRating.objects.filter(pk=instance.pk).values("stars").first()
    instance._old_stars = old["stars"] if old else None


@receiver(post_save, sender=DriverRating)
def driver_rating_post_save(sender, instance: DriverRating, created: bool, **kwargs):
    from accounts.models import DriverProfile

    def apply():
        # Ensure we are in a transaction for select_for_update
        with transaction.atomic():
            # Lock row to avoid races if many ratings happen concurrently
            driver = DriverProfile.objects.select_for_update().get(pk=instance.driver_id)

            if created:
                driver.rating_sum += int(instance.stars)
                driver.rating_count += 1
            else:
                old = getattr(instance, "_old_stars", None)
                if old is None:
                    # fallback safety: treat as created (shouldn't happen if pre_save ran)
                    driver.rating_sum += int(instance.stars)
                    driver.rating_count += 1
                else:
                    delta = int(instance.stars) - int(old)
                    driver.rating_sum += delta

            driver.avg_rating = _recompute_avg(driver.rating_sum, driver.rating_count)
            driver.save(update_fields=["rating_sum", "rating_count", "avg_rating"])

    transaction.on_commit(apply)


@receiver(post_delete, sender=DriverRating)
def driver_rating_post_delete(sender, instance: DriverRating, **kwargs):
    from accounts.models import DriverProfile

    def apply():
        with transaction.atomic():
            driver = DriverProfile.objects.select_for_update().get(pk=instance.driver_id)
            driver.rating_sum -= int(instance.stars)
            driver.rating_count = max(0, int(driver.rating_count) - 1)

            # Safety clamp: sum shouldn't go below 0, but don't hide bugs silently in dev
            if driver.rating_count == 0:
                driver.rating_sum = 0

            driver.avg_rating = _recompute_avg(driver.rating_sum, driver.rating_count)
            driver.save(update_fields=["rating_sum", "rating_count", "avg_rating"])

    transaction.on_commit(apply)


# ----- Branch rating signals -----

@receiver(pre_save, sender=BranchRating)
def branch_rating_pre_save(sender, instance: BranchRating, **kwargs):
    if not instance.pk:
        instance._old_stars = None
        return
    old = BranchRating.objects.filter(pk=instance.pk).values("stars").first()
    instance._old_stars = old["stars"] if old else None


@receiver(post_save, sender=BranchRating)
def branch_rating_post_save(sender, instance: BranchRating, created: bool, **kwargs):
    from accounts.models import Branch

    def apply():
        with transaction.atomic():
            branch = Branch.objects.select_for_update().get(pk=instance.branch_id)

            if created:
                branch.rating_sum += int(instance.stars)
                branch.rating_count += 1
            else:
                old = getattr(instance, "_old_stars", None)
                if old is None:
                    branch.rating_sum += int(instance.stars)
                    branch.rating_count += 1
                else:
                    branch.rating_sum += int(instance.stars) - int(old)

            branch.avg_rating = _recompute_avg(branch.rating_sum, branch.rating_count)
            branch.save(update_fields=["rating_sum", "rating_count", "avg_rating"])

    transaction.on_commit(apply)


@receiver(post_delete, sender=BranchRating)
def branch_rating_post_delete(sender, instance: BranchRating, **kwargs):
    from accounts.models import Branch

    def apply():
        with transaction.atomic():
            branch = Branch.objects.select_for_update().get(pk=instance.branch_id)
            branch.rating_sum -= int(instance.stars)
            branch.rating_count = max(0, int(branch.rating_count) - 1)
            if branch.rating_count == 0:
                branch.rating_sum = 0

            branch.avg_rating = _recompute_avg(branch.rating_sum, branch.rating_count)
            branch.save(update_fields=["rating_sum", "rating_count", "avg_rating"])

    transaction.on_commit(apply)
