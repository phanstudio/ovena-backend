from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0048_alter_primaryagent_created_by_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessadmin",
            name="transaction_pin_hash",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]
