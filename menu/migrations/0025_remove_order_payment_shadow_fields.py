from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0024_orderitem_addtional_note"),
    ]

    operations = [
        migrations.RemoveField(model_name="order", name="payment_reference"),
        migrations.RemoveField(model_name="order", name="payment_initialized_at"),
        migrations.RemoveField(model_name="order", name="payment_completed_at"),
    ]
