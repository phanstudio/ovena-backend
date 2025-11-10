from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Branch, BaseItem, BaseItemAvailability

# might change to celery later
@receiver(post_save, sender=Branch)
def create_availability_for_new_branch(sender, instance, created, **kwargs):
    if created:
        items = BaseItem.objects.all()
        availabilities = [
            BaseItemAvailability(branch=instance, base_item=item, is_available=True)
            for item in items
        ]
        BaseItemAvailability.objects.bulk_create(availabilities, ignore_conflicts=True)

@receiver(post_save, sender=BaseItem)
def create_branch_availability_for_new_item(sender, instance, created, **kwargs):
    if created:
        branches = Branch.objects.all()
        availabilities = [
            BaseItemAvailability(branch=branch, base_item=instance, is_available=True)
            for branch in branches
        ]
        BaseItemAvailability.objects.bulk_create(availabilities, ignore_conflicts=True)
