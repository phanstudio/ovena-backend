from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Branch, MenuItem, MenuItemAvailability

@receiver(post_save, sender=Branch)
def create_availability_for_new_branch(sender, instance, created, **kwargs):
    if created:
        items = MenuItem.objects.all()
        availabilities = [
            MenuItemAvailability(branch=instance, item=item, is_available=True)
            for item in items
        ]
        MenuItemAvailability.objects.bulk_create(availabilities, ignore_conflicts=True)

@receiver(post_save, sender=MenuItem)
def create_branch_availability(sender, instance, created, **kwargs):
    if created:
        branches = instance.category.menu.restaurant.branches.all()
        availabilities = [
            MenuItemAvailability(branch=branch, item=instance, is_available=True)
            for branch in branches
        ]
        MenuItemAvailability.objects.bulk_create(availabilities, ignore_conflicts=True)
