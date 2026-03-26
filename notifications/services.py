from django.utils import timezone

from accounts.models import DriverProfile
from driver_api.models import DriverNotification


def get_driver_notifications_queryset(driver: DriverProfile):
    return DriverNotification.objects.filter(driver=driver).order_by("-created_at")


def get_driver_unread_count(driver: DriverProfile) -> int:
    return DriverNotification.objects.filter(driver=driver, is_read=False).count()


def mark_notifications_read(queryset):
    now = timezone.now()
    return queryset.filter(is_read=False).update(is_read=True, read_at=now)

