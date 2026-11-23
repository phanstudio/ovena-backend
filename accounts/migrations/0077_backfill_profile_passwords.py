from django.contrib.auth.hashers import is_password_usable
from django.db import migrations


def backfill_profile_passwords(apps, schema_editor):
    DriverProfile = apps.get_model("accounts", "DriverProfile")
    BusinessAdmin = apps.get_model("accounts", "BusinessAdmin")
    AppAdmin = apps.get_model("admin_api", "AppAdmin")

    for model in (DriverProfile, BusinessAdmin, AppAdmin):
        to_update = []
        for profile in model.objects.select_related("user").filter(password_hash=""):
            user_pwd = getattr(profile.user, "password", "")
            if user_pwd and is_password_usable(user_pwd):
                profile.password_hash = user_pwd
                to_update.append(profile)
        if to_update:
            model.objects.bulk_update(to_update, ["password_hash"], batch_size=500)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0076_add_profile_password_hash"),
        ("admin_api", "0003_add_appadmin_password_hash"),
    ]

    operations = [
        migrations.RunPython(backfill_profile_passwords, noop_reverse),
    ]
