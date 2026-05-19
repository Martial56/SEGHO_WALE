from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "DROP INDEX IF EXISTS facturation_facture_consultation_id_764bb969",
                "ALTER TABLE facturation_facture DROP COLUMN consultation_id",
            ],
            reverse_sql="",
        ),
    ]
