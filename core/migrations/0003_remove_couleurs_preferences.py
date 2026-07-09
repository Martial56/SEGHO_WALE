from django.db import migrations


def drop_column_if_exists(apps, schema_editor):
    """Supprime couleurs_preferences seulement si elle existe.

    La colonne a été ajoutée à la main sur des bases anciennes, jamais via
    une migration (0001/0002 ne la créent pas) — sur une base neuve
    (tests, CI, nouvelle install), le DROP COLUMN brut échouait donc avec
    "no such column".
    """
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        columns = [c.name for c in connection.introspection.get_table_description(cursor, 'core_userprofile')]
    if 'couleurs_preferences' in columns:
        schema_editor.execute("ALTER TABLE core_userprofile DROP COLUMN couleurs_preferences;")


def add_column_back(apps, schema_editor):
    schema_editor.execute("ALTER TABLE core_userprofile ADD COLUMN couleurs_preferences TEXT NOT NULL DEFAULT '';")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_add_log_activite_generique'),
    ]

    operations = [
        migrations.RunPython(drop_column_if_exists, add_column_back),
    ]
