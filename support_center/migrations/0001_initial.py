from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0049_businessadmin_transaction_pin_hash"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessSupportTicket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(blank=True, default="general", max_length=80)),
                ("subject", models.CharField(max_length=200)),
                ("description", models.TextField()),
                ("status", models.CharField(choices=[("open", "Open"), ("in_progress", "In Progress"), ("resolved", "Resolved"), ("closed", "Closed")], default="open", max_length=20)),
                ("priority", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")], default="medium", max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("assigned_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_business_support_tickets", to=settings.AUTH_USER_MODEL)),
                ("business_admin", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="support_tickets", to="accounts.businessadmin")),
            ],
            options={
                "indexes": [models.Index(fields=["business_admin", "status", "-created_at"], name="support_cen_busines_6d3655_idx")],
            },
        ),
        migrations.CreateModel(
            name="BusinessSupportTicketMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sender_type", models.CharField(choices=[("admin", "Admin"), ("support", "Support"), ("system", "System")], max_length=10)),
                ("sender_id", models.IntegerField(blank=True, null=True)),
                ("message", models.TextField()),
                ("attachments_json", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="support_center.businesssupportticket")),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
    ]
