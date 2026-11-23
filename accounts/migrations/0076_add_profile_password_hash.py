from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0075_alter_businesscerd_business_doc_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessadmin",
            name="password_hash",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="customerprofile",
            name="password_hash",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="driverprofile",
            name="password_hash",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="primaryagent",
            name="password_hash",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]
