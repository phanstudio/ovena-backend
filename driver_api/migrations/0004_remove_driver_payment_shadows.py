from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("driver_api", "0003_remove_supportticket_assigned_to_and_more"),
    ]

    operations = [
        migrations.DeleteModel(name="DriverWallet"),
        migrations.DeleteModel(name="DriverLedgerEntry"),
        migrations.DeleteModel(name="DriverWithdrawalRequest"),
    ]
