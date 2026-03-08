from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("driver_api", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="driverwithdrawalrequest",
            name="payment_withdrawal",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="driver_withdrawal",
                to="payments.withdrawal",
            ),
        ),
    ]
