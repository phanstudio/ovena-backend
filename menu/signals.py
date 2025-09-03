from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Branch, MenuItem, MenuItemAvailability

@receiver(post_save, sender=Branch)
def create_availability_for_new_branch(sender, instance, created, **kwargs):
    if created:
        for item in MenuItem.objects.all():
            MenuItemAvailability.objects.get_or_create(
                branch=instance,
                item=item,
                defaults={"is_available": True}  # no override, falls back to item.price
            )

@receiver(post_save, sender=MenuItem)
def create_branch_availability(sender, instance, created, **kwargs):
    if created:
        for branch in instance.category.menu.restaurant.branches.all():
            MenuItemAvailability.objects.get_or_create(
                branch=branch,
                item=instance,
                defaults={"is_available": True}
            )
