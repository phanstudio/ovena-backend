from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("admin_api", "0002_alter_appadmin_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="appadmin",
            name="password_hash",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]
