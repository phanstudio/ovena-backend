from driver_api.models import SupportFAQItem
from support_center.models import SupportTicket, SupportTicketMessage, SupportTicketAttachment
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
    return SupportFAQItem.objects.filter(
        is_active=True, category__is_active=True
    ).select_related("category")


def get_driver_open_ticket_count(driver: User) -> int:
    return SupportTicket.objects.filter(
        owner_id=driver.user_id,
        owner_role=SupportTicket.OWNER_DRIVER,
        status__in=[SupportTicket.STATUS_OPEN, SupportTicket.STATUS_IN_PROGRESS],
    ).count()


def create_support_ticket_message(
    role: SenderRole | Role,
    ticket: SupportTicket,
    *,
    message: str,
    user: User | None = None,
    attachment_files: list | None = None,
):

    ticket_message = SupportTicketMessage.objects.create(
        ticket=ticket,
        sender=user,
        sender_type=role.value,
        message=message,
    )

    if attachment_files:
        create_ticket_attachments(ticket_message, attachment_files, uploaded_by=user)

    return ticket_message


def create_ticket_attachments(
    message: SupportTicketMessage,
    files: list,
    *,
    uploaded_by: User | None = None,
):
    # Saved individually (not bulk_create) so each FileField actually gets
    # written to storage via the normal save-time pre_save hook.
    attachments = []
    for f in files:
        attachment = SupportTicketAttachment(
            message=message,
            file=f,
            original_filename=getattr(f, "name", ""),
            content_type=getattr(f, "content_type", ""),
            file_size=getattr(f, "size", 0),
            uploaded_by=uploaded_by,
        )
        attachment.save()
        attachments.append(attachment)
    return attachments


def create_support_ticket_obj(
    *,
    owner: User,
    role: Role,
    subject: str,
    message: str,
    description: str = "",
    category: str = "general",
    status: str = SupportTicket.STATUS_OPEN,
    priority: str = SupportTicket.PRIORITY_MEDIUM,
    created_by: User = None,
    created_by_type: str = SupportTicket.CREATED_BY_USER,
    assigned_to: User = None,
    attachment_files: list | None = None,
):
    check_user_role(owner, role)

    ticket = SupportTicket.objects.create(
        owner=owner,
        owner_role=role.value,
        subject=subject,
        description=description,
        category=category,
        status=status,
        priority=priority,
        created_by=created_by,
        created_by_type=created_by_type,
        assigned_to=assigned_to,
    )

    create_support_ticket_message(
        role, ticket, message=message, user=owner, attachment_files=attachment_files
    )
    return ticket


def create_support_ticket(
    user: User,
    role: Role,
    *,
    subject: str,
    message: str,
    description: str = "",
    category: str = "general",
    priority: str = SupportTicket.PRIORITY_LOW,
    attachment_files: list | None = None,
):
    return create_support_ticket_obj(
        owner=user,
        role=role,
        subject=subject,
        message=message,
        description=description,
        category=category,
        priority=priority,
        created_by=user,
        attachment_files=attachment_files,
    )


def create_system_support_ticket(
    owner: User,
    role: Role,
    created_by_type: SenderRole,
    *,
    subject: str,
    message: str,
    created_by: User,
    description: str = "",
    category: str = "general",
    priority: str = SupportTicket.PRIORITY_LOW,
    attachment_files: list | None = None,
):
    if created_by_type == SenderRole.SENDER_SUPPORT and created_by == None:
        raise ValueError("Created by should only be None for system created tickects.")
    return create_support_ticket_obj(
        owner=owner,
        role=role,
        subject=subject,
        message=message,
        description=description,
        category=category,
        priority=priority,
        created_by=created_by,
        created_by_type=created_by_type.value,
        assigned_to=created_by,
        attachment_files=attachment_files,
    )


def check_user_role(user: User, role: Role | SenderRole):
    if role.value == Role.OWNER_CUSTOMER.value and not getattr(
        user, "customer_profile", None
    ):
        raise RoleError("User is not a customer")

    if role.value == Role.OWNER_DRIVER.value and not getattr(
        user, "driver_profile", None
    ):
        raise RoleError("User is not a driver")

    if role.value == Role.OWNER_BUSINESS_ADMIN.value and not getattr(
        user, "business_admin", None
    ):
        raise RoleError("User is not a business admin")

    if role.value == Role.OWNER_BUSINESS_STAFF.value and not getattr(
        user, "primary_agent", None
    ):
        raise RoleError("User is not business staff")

    if isinstance(role, SenderRole):
        return
    # leaving space for support role checks


def create_user_reply(
    user: User, role: Role | SenderRole, ticket: SupportTicket, **kwargs
):
    check_user_role(user, role)
    return create_support_ticket_message(role, ticket, user=user, **kwargs)


def create_system_reply(ticket: SupportTicket, message: str):
    return create_support_ticket_message(
        SenderRole.SENDER_SYSTEM, ticket, message=message
    )
