from celery import shared_task
from django.contrib.auth import get_user_model
from support_center.models import SupportTicket
from admin_api.models import AppAdmin
from .services import Role, create_system_support_ticket, SenderRole
from django.db import transaction
from notifications.services import create_notification, Notification

User = get_user_model()


@shared_task
def auto_assign_ticket(ticket_id: int):
    try:
        ticket = SupportTicket.objects.get(id=ticket_id)
    except SupportTicket.DoesNotExist:
        return

    assign(ticket)

def assign(ticket: SupportTicket):
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

@shared_task
def create_system_ticket(
    user, role: Role, 
    *,
    subject: str,
    message: str,
    description: str = "",
    category: str = "system",
    ):
    with transaction.atomic():
        ticket = create_system_support_ticket(
            user=user,
            role=role,
            created_by_type= SenderRole.SENDER_SYSTEM,
            subject=subject,
            message=message,
            category=category,
            priority=SupportTicket.PRIORITY_HIGH,
            description=description,
        )

        create_notification(
            user=user, 
            title=f"{subject} (support ticket)", 
            notification_type= Notification.TYPE_SYSTEM, 
            payload= {"message": "Support ticket created."}
        )

        assign(ticket)
