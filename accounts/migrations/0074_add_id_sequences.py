from django.db import migrations

ADD_SEQUENCES_SQL = """
-- CustomerProfile sequence
CREATE SEQUENCE IF NOT EXISTS accounts_customerprofile_id_seq;
SELECT setval('accounts_customerprofile_id_seq', COALESCE((SELECT MAX(id) FROM accounts_customerprofile), 0) + 1, false);
ALTER TABLE accounts_customerprofile ALTER COLUMN id SET DEFAULT nextval('accounts_customerprofile_id_seq');
ALTER SEQUENCE accounts_customerprofile_id_seq OWNED BY accounts_customerprofile.id;

-- DriverProfile sequence
CREATE SEQUENCE IF NOT EXISTS accounts_driverprofile_id_seq;
SELECT setval('accounts_driverprofile_id_seq', COALESCE((SELECT MAX(id) FROM accounts_driverprofile), 0) + 1, false);
ALTER TABLE accounts_driverprofile ALTER COLUMN id SET DEFAULT nextval('accounts_driverprofile_id_seq');
ALTER SEQUENCE accounts_driverprofile_id_seq OWNED BY accounts_driverprofile.id;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0073_delete_profilebase'),
    ]

    operations = [
        migrations.RunSQL(
            sql=ADD_SEQUENCES_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
