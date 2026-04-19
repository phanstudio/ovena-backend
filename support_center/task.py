from celery import shared_task
from django.contrib.auth import get_user_model
from support_center.models import SupportTicket
from admin_api.models import AppAdmin

User = get_user_model()


@shared_task
def auto_assign_ticket(ticket_id: int):
    try:
        ticket = SupportTicket.objects.get(id=ticket_id)
    except SupportTicket.DoesNotExist:
        return

    # might add support and admin
    agent = (
        User.objects
        .filter(app_admin__role=AppAdmin.Role.SUPPORT)
        .order_by("?")
        .first()
    )

    if not agent:
        return

    ticket.assigned_to = agent
    ticket.status = SupportTicket.STATUS_IN_PROGRESS
    ticket.save(update_fields=["assigned_to", "status"])
