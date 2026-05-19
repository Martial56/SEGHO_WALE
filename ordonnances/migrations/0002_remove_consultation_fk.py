from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ordonnances', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "DROP INDEX IF EXISTS ordonnances_ordonnance_consultation_id_43296be9",
                "ALTER TABLE ordonnances_ordonnance DROP COLUMN consultation_id",
            ],
            reverse_sql="",
        ),
    ]
