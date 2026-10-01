import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


MIGRATE_MTI_TO_STANDALONE_SQL = """
-- 1. Add user_id, referral_code, created_at to accounts_customerprofile if not exists
ALTER TABLE accounts_customerprofile ADD COLUMN IF NOT EXISTS user_id bigint;
ALTER TABLE accounts_customerprofile ADD COLUMN IF NOT EXISTS referral_code varchar(20);
ALTER TABLE accounts_customerprofile ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();

-- 2. Populate accounts_customerprofile from accounts_profilebase
UPDATE accounts_customerprofile c
SET user_id = p.user_id,
    referral_code = p.referral_code,
    created_at = p.created_at
FROM accounts_profilebase p
WHERE c.profilebase_ptr_id = p.id;

-- 3. Add user_id, referral_code, created_at to accounts_driverprofile if not exists
ALTER TABLE accounts_driverprofile ADD COLUMN IF NOT EXISTS user_id bigint;
ALTER TABLE accounts_driverprofile ADD COLUMN IF NOT EXISTS referral_code varchar(20);
ALTER TABLE accounts_driverprofile ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();

-- 4. Populate accounts_driverprofile from accounts_profilebase
UPDATE accounts_driverprofile d
SET user_id = p.user_id,
    referral_code = p.referral_code,
    created_at = p.created_at
FROM accounts_profilebase p
WHERE d.profilebase_ptr_id = p.id;

-- 5. Drop foreign key constraints to accounts_profilebase
ALTER TABLE accounts_customerprofile DROP CONSTRAINT IF EXISTS accounts_customerpro_profilebase_ptr_id_19085bec_fk_accounts_;
ALTER TABLE accounts_driverprofile DROP CONSTRAINT IF EXISTS accounts_driverprofi_profilebase_ptr_id_c7c5e56c_fk_accounts_;

-- 6. Rename profilebase_ptr_id to id in both tables
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'accounts_customerprofile' AND column_name = 'profilebase_ptr_id'
    ) THEN
        ALTER TABLE accounts_customerprofile RENAME COLUMN profilebase_ptr_id TO id;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'accounts_driverprofile' AND column_name = 'profilebase_ptr_id'
    ) THEN
        ALTER TABLE accounts_driverprofile RENAME COLUMN profilebase_ptr_id TO id;
    END IF;
END $$;

-- 7. Add foreign key and unique constraints for user_id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'accounts_customerprofile_user_id_fk_accounts_user_id'
    ) THEN
        ALTER TABLE accounts_customerprofile 
        ADD CONSTRAINT accounts_customerprofile_user_id_fk_accounts_user_id 
        FOREIGN KEY (user_id) REFERENCES accounts_user(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'accounts_customerprofile_user_id_key'
    ) THEN
        ALTER TABLE accounts_customerprofile ADD CONSTRAINT accounts_customerprofile_user_id_key UNIQUE (user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'accounts_driverprofile_user_id_fk_accounts_user_id'
    ) THEN
        ALTER TABLE accounts_driverprofile 
        ADD CONSTRAINT accounts_driverprofile_user_id_fk_accounts_user_id 
        FOREIGN KEY (user_id) REFERENCES accounts_user(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'accounts_driverprofile_user_id_key'
    ) THEN
        ALTER TABLE accounts_driverprofile ADD CONSTRAINT accounts_driverprofile_user_id_key UNIQUE (user_id);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS accounts_customerprofile_referral_code_key ON accounts_customerprofile (referral_code) WHERE referral_code IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS accounts_driverprofile_referral_code_key ON accounts_driverprofile (referral_code) WHERE referral_code IS NOT NULL;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0071_businessonboardstatus_checked"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=MIGRATE_MTI_TO_STANDALONE_SQL,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                # 1. CustomerProfile state updates
                migrations.RemoveField(
                    model_name="customerprofile",
                    name="profilebase_ptr",
                ),
                migrations.AddField(
                    model_name="customerprofile",
                    name="id",
                    field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                migrations.AddField(
                    model_name="customerprofile",
                    name="user",
                    field=models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="customer_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AddField(
                    model_name="customerprofile",
                    name="referral_code",
                    field=models.CharField(blank=True, db_index=True, max_length=20, null=True, unique=True),
                ),
                migrations.AddField(
                    model_name="customerprofile",
                    name="created_at",
                    field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
                    preserve_default=False,
                ),

                # 2. DriverProfile state updates
                migrations.RemoveField(
                    model_name="driverprofile",
                    name="profilebase_ptr",
                ),
                migrations.AddField(
                    model_name="driverprofile",
                    name="id",
                    field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                migrations.AddField(
                    model_name="driverprofile",
                    name="user",
                    field=models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="driver_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AddField(
                    model_name="driverprofile",
                    name="referral_code",
                    field=models.CharField(blank=True, db_index=True, max_length=20, null=True, unique=True),
                ),
                migrations.AddField(
                    model_name="driverprofile",
                    name="created_at",
                    field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
                    preserve_default=False,
                ),
            ],
        ),
    ]
