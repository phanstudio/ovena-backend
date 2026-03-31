from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def forward_copy_support_data(apps, schema_editor):
    SupportTicket = apps.get_model("support_center", "SupportTicket")
    SupportTicketMessage = apps.get_model("support_center", "SupportTicketMessage")
    DriverSupportTicket = apps.get_model("driver_api", "SupportTicket")
    DriverSupportTicketMessage = apps.get_model("driver_api", "SupportTicketMessage")
    BusinessSupportTicket = apps.get_model("support_center", "BusinessSupportTicket")
    BusinessSupportTicketMessage = apps.get_model("support_center", "BusinessSupportTicketMessage")

    driver_ticket_map = {}
    for legacy in DriverSupportTicket.objects.all().iterator():
        ticket = SupportTicket.objects.create(
            owner_user_id=getattr(getattr(legacy, "driver", None), "user_id", None),
            owner_role="driver",
            driver_id=legacy.driver_id,
            category=legacy.category,
            subject=legacy.subject,
            description=legacy.description,
            status=legacy.status,
            priority=legacy.priority,
            is_blocking=legacy.is_blocking,
            assigned_to_id=legacy.assigned_to_id,
            created_at=legacy.created_at,
            closed_at=legacy.closed_at,
            updated_at=legacy.updated_at,
        )
        driver_ticket_map[legacy.id] = ticket.id

    business_ticket_map = {}
    for legacy in BusinessSupportTicket.objects.all().iterator():
        ticket = SupportTicket.objects.create(
            owner_user_id=getattr(getattr(legacy, "business_admin", None), "user_id", None),
            owner_role="business_admin",
            business_admin_id=legacy.business_admin_id,
            category=legacy.category,
            subject=legacy.subject,
            description=legacy.description,
            status=legacy.status,
            priority=legacy.priority,
            is_blocking=False,
            assigned_to_id=legacy.assigned_to_id,
            created_at=legacy.created_at,
            closed_at=legacy.closed_at,
            updated_at=legacy.updated_at,
        )
        business_ticket_map[legacy.id] = ticket.id

    message_rows = []
    for legacy in DriverSupportTicketMessage.objects.all().iterator():
        target_ticket_id = driver_ticket_map.get(legacy.ticket_id)
        if target_ticket_id:
            message_rows.append(
                SupportTicketMessage(
                    ticket_id=target_ticket_id,
                    sender_type=legacy.sender_type,
                    sender_id=legacy.sender_id,
                    message=legacy.message,
                    attachments_json=legacy.attachments_json,
                    created_at=legacy.created_at,
                )
            )

    for legacy in BusinessSupportTicketMessage.objects.all().iterator():
        target_ticket_id = business_ticket_map.get(legacy.ticket_id)
        if target_ticket_id:
            sender_type = "business_admin" if legacy.sender_type == "admin" else legacy.sender_type
            message_rows.append(
                SupportTicketMessage(
                    ticket_id=target_ticket_id,
                    sender_type=sender_type,
                    sender_id=legacy.sender_id,
                    message=legacy.message,
                    attachments_json=legacy.attachments_json,
                    created_at=legacy.created_at,
                )
            )

    if message_rows:
        SupportTicketMessage.objects.bulk_create(message_rows)


class Migration(migrations.Migration):

    dependencies = [
        ("driver_api", "0001_initial"),
        ("support_center", "0002_rename_support_cen_busines_6d3655_idx_support_cen_busines_e339d6_idx"),
        ("accounts", "0049_businessadmin_transaction_pin_hash"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SupportTicket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("owner_role", models.CharField(choices=[("driver", "Driver"), ("business_admin", "Business Admin")], max_length=20)),
                ("category", models.CharField(blank=True, default="general", max_length=80)),
                ("subject", models.CharField(max_length=200)),
                ("description", models.TextField()),
                ("status", models.CharField(choices=[("open", "Open"), ("in_progress", "In Progress"), ("resolved", "Resolved"), ("closed", "Closed")], default="open", max_length=20)),
                ("priority", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")], default="medium", max_length=10)),
                ("is_blocking", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assigned_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_support_tickets_central", to=settings.AUTH_USER_MODEL)),
                ("business_admin", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="central_support_tickets", to="accounts.businessadmin")),
                ("driver", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="central_support_tickets", to="accounts.driverprofile")),
                ("owner_user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="owned_support_tickets", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["owner_role", "status", "-created_at"], name="support_cen_owner_r_8f0f80_idx"),
                    models.Index(fields=["driver", "status", "-created_at"], name="support_cen_driver__dcdf7d_idx"),
                    models.Index(fields=["business_admin", "status", "-created_at"], name="support_cen_busines_1c7cf5_idx"),
                    models.Index(fields=["is_blocking", "status"], name="support_cen_is_bloc_6bc770_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="SupportTicketMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sender_type", models.CharField(choices=[("driver", "Driver"), ("business_admin", "Business Admin"), ("support", "Support"), ("system", "System")], max_length=20)),
                ("sender_id", models.IntegerField(blank=True, null=True)),
                ("message", models.TextField()),
                ("attachments_json", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="support_center.supportticket")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.RunPython(forward_copy_support_data, migrations.RunPython.noop),
        migrations.DeleteModel(name="BusinessSupportTicketMessage"),
        migrations.DeleteModel(name="BusinessSupportTicket"),
    ]
