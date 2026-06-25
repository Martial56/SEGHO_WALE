from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_add_log_activite_generique'),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE core_userprofile DROP COLUMN couleurs_preferences;",
            reverse_sql="ALTER TABLE core_userprofile ADD COLUMN couleurs_preferences TEXT NOT NULL DEFAULT '';",
        ),
    ]
