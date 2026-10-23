# Generated manually for payout and ledger security hardening

import django.db.models.deletion
from django.db import migrations, models


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
        migrations.AddConstraint(
            model_name='ledgerentry',
            constraint=models.UniqueConstraint(fields=('user', 'seq'), name='uniq_ledger_entry_user_seq'),
        ),
    ]
