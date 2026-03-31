from driver_api.models import SupportFAQItem
from support_center.models import SupportTicket, SupportTicketMessage
from accounts.models import User
from enum import Enum

class RoleError(ValueError):
    """Role error"""
    ...

class Role(Enum):
    OWNER_DRIVER = "driver"
    OWNER_BUSINESS_STAFF = "business_staff"
    OWNER_CUSTOMER = "customer"
    OWNER_BUSINESS_ADMIN = "business_admin"
    UNKNOWN = "UNKNOWN"

class SenderRole(Enum):
    SENDER_SUPPORT = "support"
    SENDER_SYSTEM = "system"

def get_active_faq_queryset():
    return SupportFAQItem.objects.filter(is_active=True, category__is_active=True).select_related("category")

def get_driver_open_ticket_count(driver: User) -> int:
    return SupportTicket.objects.filter(
        owner=driver,
        owner_role=SupportTicket.OWNER_DRIVER,
        status__in=[SupportTicket.STATUS_OPEN, SupportTicket.STATUS_IN_PROGRESS],
    ).count()

def create_support_ticket_message(
    role: SenderRole | Role, ticket: SupportTicket, *,
    message: str, user: User | None = None, attachments_json: list | None = None,
):

    return SupportTicketMessage.objects.create(
        ticket=ticket,
        sender=user,
        sender_type=role.value,
        message=message,
        attachments_json=attachments_json or [],
    )

def create_support_ticket(
        user:User, role:Role, *, status:str = SupportTicket.STATUS_OPEN, 
        priority:str = SupportTicket.PRIORITY_LOW, category:str = "general",
        subject:str, message:str, description:str = "", 
    ):
    check_user_role(user, role)
    ticket = SupportTicket.objects.create(
        owner=user,
        owner_role=role.value,
        subject=subject,
        status=status,
        priority=priority,
        description=description,
        category=category
    )
    create_support_ticket_message(role, ticket, message=message, user=user)
    return ticket

def check_user_role(user:User, role:Role|SenderRole):
    if role.value == Role.OWNER_CUSTOMER.value and not getattr(user, "customer_profile", None):
        raise RoleError("User is not a customer")

    if role.value == Role.OWNER_DRIVER.value and not getattr(user, "driver_profile", None):
        raise RoleError("User is not a driver")

    if role.value == Role.OWNER_BUSINESS_ADMIN.value and not getattr(user, "business_admin", None):
        raise RoleError("User is not a business admin")

    if role.value == Role.OWNER_BUSINESS_STAFF.value and not getattr(user, "primaryagent", None):
        raise RoleError("User is not business staff")
    
    if isinstance(role, SenderRole):
        return
    # leaving space for support role checks

def create_user_reply(user:User, role:Role|SenderRole, ticket:SupportTicket, **kwargs):
    check_user_role(user, role)
    return create_support_ticket_message(role, ticket, user=user, **kwargs)

def create_system_reply(ticket:SupportTicket, message: str):
    return create_support_ticket_message(SenderRole.SENDER_SYSTEM, ticket, message=message)
