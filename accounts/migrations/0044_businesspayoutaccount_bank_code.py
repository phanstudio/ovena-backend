from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0043_alter_businessadmin_business"),
    ]

    operations = [
        migrations.AddField(
            model_name="businesspayoutaccount",
            name="bank_code",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
    ]
