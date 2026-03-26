from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0042_alter_customerprofile_profilebase_ptr_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DriverWallet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("current_balance", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("available_balance", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("pending_balance", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("last_settled_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "driver",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="wallet",
                        to="accounts.driverprofile",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="DriverLedgerEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entry_type", models.CharField(choices=[("credit", "Credit"), ("debit", "Debit"), ("hold", "Hold"), ("release", "Release")], max_length=12)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("source_type", models.CharField(blank=True, default="", max_length=50)),
                ("source_id", models.CharField(blank=True, default="", max_length=100)),
                ("status", models.CharField(choices=[("posted", "Posted"), ("pending", "Pending"), ("failed", "Failed")], default="posted", max_length=12)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "driver",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ledger_entries", to="accounts.driverprofile"),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["driver", "-created_at"], name="driver_api_d_driver__7d94df_idx"), models.Index(fields=["source_type", "source_id"], name="driver_api_d_source__af04ed_idx")],
            },
        ),
        migrations.CreateModel(
            name="DriverNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("notification_type", models.CharField(choices=[("generic", "Generic"), ("order", "Order"), ("earning", "Earning"), ("withdrawal", "Withdrawal"), ("support", "Support")], default="generic", max_length=20)),
                ("title", models.CharField(max_length=160)),
                ("body", models.TextField()),
                ("payload_json", models.JSONField(blank=True, default=dict)),
                ("is_read", models.BooleanField(db_index=True, default=False)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "driver",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="accounts.driverprofile"),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["driver", "is_read", "-created_at"], name="driver_api_d_driver__ee6cd3_idx")],
            },
        ),
        migrations.CreateModel(
            name="DriverWithdrawalRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("status", models.CharField(choices=[("requested", "Requested"), ("auto_rejected", "Auto Rejected"), ("approved", "Approved"), ("processing", "Processing"), ("paid", "Paid"), ("failed", "Failed"), ("cancelled", "Cancelled")], default="requested", max_length=20)),
                ("bank_snapshot", models.JSONField(blank=True, default=dict)),
                ("idempotency_key", models.CharField(max_length=128)),
                ("review_snapshot", models.JSONField(blank=True, default=dict)),
                ("transfer_ref", models.CharField(blank=True, default="", max_length=120)),
                ("failure_reason", models.TextField(blank=True, default="")),
                ("retry_count", models.PositiveSmallIntegerField(default=0)),
                ("needs_manual_review", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "driver",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="withdrawals", to="accounts.driverprofile"),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["driver", "status", "-created_at"], name="driver_api_d_driver__4cf15e_idx")],
                "constraints": [models.UniqueConstraint(fields=("driver", "idempotency_key"), name="uniq_driver_withdrawal_idempotency")],
            },
        ),
        migrations.CreateModel(
            name="SupportFAQCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["sort_order", "name"]},
        ),
        migrations.CreateModel(
            name="SupportFAQItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("question", models.CharField(max_length=255)),
                ("answer", models.TextField()),
                ("tags", models.JSONField(blank=True, default=list)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "category",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="faqs", to="driver_api.supportfaqcategory"),
                ),
            ],
            options={"ordering": ["category__sort_order", "sort_order", "id"]},
        ),
        migrations.CreateModel(
            name="SupportTicket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(blank=True, default="general", max_length=80)),
                ("subject", models.CharField(max_length=200)),
                ("description", models.TextField()),
                ("status", models.CharField(choices=[("open", "Open"), ("in_progress", "In Progress"), ("resolved", "Resolved"), ("closed", "Closed")], default="open", max_length=20)),
                ("priority", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")], default="medium", max_length=10)),
                ("is_blocking", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assigned_to",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_support_tickets", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "driver",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="support_tickets", to="accounts.driverprofile"),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["driver", "status", "-created_at"], name="driver_api_s_driver__5f6b7b_idx"), models.Index(fields=["is_blocking", "status"], name="driver_api_s_is_blo_9f8a93_idx")],
            },
        ),
        migrations.CreateModel(
            name="SupportTicketMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sender_type", models.CharField(choices=[("driver", "Driver"), ("admin", "Admin"), ("system", "System")], max_length=10)),
                ("sender_id", models.IntegerField(blank=True, null=True)),
                ("message", models.TextField()),
                ("attachments_json", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "ticket",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="driver_api.supportticket"),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
    ]

