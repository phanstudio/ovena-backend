from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("coupons_discount", "0001_initial"),
        ("menu", "0012_alter_order_coupons_delete_coupons"),
    ]

    operations = [
        migrations.AddField(
            model_name="coupons",
            name="buy_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="buy_coupons",
                to="menu.menuitem",
            ),
        ),
        migrations.AddField(
            model_name="coupons",
            name="get_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="get_coupons",
                to="menu.menuitem",
            ),
        ),
    ]
