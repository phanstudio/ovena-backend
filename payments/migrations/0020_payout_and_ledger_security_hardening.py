# Generated manually for payout and ledger security hardening

import hashlib
import os

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Count


def backfill_ledger_sequences(apps, schema_editor):
    """Assign per-user sequence numbers and rebuild hashes that include them."""
    LedgerEntry = apps.get_model("payments", "LedgerEntry")
    database = schema_editor.connection.alias
    duplicate_user_ids = (
        LedgerEntry.objects.using(database)
        .values("user_id", "seq")
        .annotate(row_count=Count("pk"))
        .filter(row_count__gt=1)
        .values("user_id")
        .distinct()
    )
    entries = (
        LedgerEntry.objects.using(database)
        .filter(user_id__in=duplicate_user_ids)
        .order_by("user_id", "created_at", "pk")
    )

    if not entries.exists():
        return

    salt = os.environ.get("LEDGER_HASH_SALT", "")
    if not salt:
        raise RuntimeError("LEDGER_HASH_SALT must be configured to migrate ledger entries.")

    disabled_triggers = []
    table_name = schema_editor.connection.ops.quote_name(LedgerEntry._meta.db_table)
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT trigger.tgname, trigger.tgenabled
                FROM pg_trigger AS trigger
                JOIN pg_proc AS function ON function.oid = trigger.tgfoid
                WHERE trigger.tgrelid = %s::regclass
                  AND NOT trigger.tgisinternal
                  AND function.proname = %s
                """,
                [LedgerEntry._meta.db_table, "prevent_ledger_update"],
            )
            disabled_triggers = cursor.fetchall()
            for trigger_name, _ in disabled_triggers:
                cursor.execute(
                    f"ALTER TABLE {table_name} DISABLE TRIGGER "
                    f"{schema_editor.connection.ops.quote_name(trigger_name)}"
                )

    current_user_id = None
    sequence = 0
    previous_hash = "GENESIS"
    batch = []
    try:
        for entry in entries.iterator(chunk_size=1000):
            if entry.user_id != current_user_id:
                current_user_id = entry.user_id
                sequence = 1
                previous_hash = "GENESIS"
            else:
                sequence += 1

            entry.seq = sequence
            entry.previous_hash = previous_hash
            sale_id = str(entry.sale_id) if entry.sale_id else "withdrawal"
            created_at = entry.created_at.isoformat()

            if entry.hash_version == 1:
                payload = (
                    f"{sale_id}|{entry.user_id}|{entry.amount}|{entry.type}|"
                    f"{entry.role}|{created_at}|{salt}"
                )
            else:
                payload = (
                    f"{sale_id}|{entry.user_id}|{entry.amount}|{entry.balance_after}|"
                    f"{entry.seq}|{entry.type}|{entry.role}|{created_at}|"
                    f"{entry.previous_hash}|{salt}"
                )

            entry.row_hash = hashlib.sha256(payload.encode()).hexdigest()
            previous_hash = entry.row_hash
            batch.append(entry)

            if len(batch) == 1000:
                LedgerEntry.objects.using(database).bulk_update(
                    batch, ["seq", "previous_hash", "row_hash"], batch_size=1000
                )
                batch.clear()

        if batch:
            LedgerEntry.objects.using(database).bulk_update(
                batch, ["seq", "previous_hash", "row_hash"], batch_size=1000
            )
    finally:
        for trigger_name, enabled_state in disabled_triggers:
            enable_mode = {
                "O": "",
                "R": " REPLICA",
                "A": " ALWAYS",
                "D": None,
            }[enabled_state]
            if enable_mode is not None:
                with schema_editor.connection.cursor() as cursor:
                    cursor.execute(
                        f"ALTER TABLE {table_name} ENABLE{enable_mode} TRIGGER "
                        f"{schema_editor.connection.ops.quote_name(trigger_name)}"
                    )


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0019_ledgerentry_hash_version_ledgerentry_seq_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sale',
            name='responsible_party',
            field=models.CharField(blank=True, choices=[('business', 'Business'), ('driver', 'Driver'), ('platform', 'Platform')], max_length=30),
        ),
        migrations.AlterField(
            model_name='withdrawal',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending_batch', 'Pending Batch'),
                    ('processing', 'Processing'),
                    ('complete', 'Complete'),
                    ('failed', 'Failed'),
                    ('cancelled', 'Cancelled'),
                    ('reversed', 'Reversed'),
                ],
                default='pending_batch',
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name='withdrawal',
            name='refund_ledger_entry',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='refunded_withdrawal',
                to='payments.ledgerentry',
            ),
        ),
        migrations.RunPython(backfill_ledger_sequences, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='ledgerentry',
            constraint=models.UniqueConstraint(fields=('user', 'seq'), name='uniq_ledger_entry_user_seq'),
        ),
    ]
