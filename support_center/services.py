from accounts.models import DriverProfile
from driver_api.models import SupportFAQItem, SupportTicket


def get_active_faq_queryset():
    return SupportFAQItem.objects.filter(is_active=True, category__is_active=True).select_related("category")


def get_driver_open_ticket_count(driver: DriverProfile) -> int:
    return SupportTicket.objects.filter(
        driver=driver,
        status__in=[SupportTicket.STATUS_OPEN, SupportTicket.STATUS_IN_PROGRESS],
    ).count()

