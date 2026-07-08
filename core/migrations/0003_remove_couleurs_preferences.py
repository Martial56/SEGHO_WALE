from django.db import migrations

TABLE = 'core_userprofile'
COLUMN = 'couleurs_preferences'


def _columns(schema_editor):
    with schema_editor.connection.cursor() as cursor:
        return [c.name for c in schema_editor.connection.introspection.get_table_description(cursor, TABLE)]


def drop_column_if_exists(apps, schema_editor):
    # Colonne présente sur les bases existantes (ajoutée hors migration) mais absente
    # d'une base créée depuis zéro (tests, nouvelle installation) : ne rien faire dans ce cas.
    if COLUMN in _columns(schema_editor):
        schema_editor.execute(f"ALTER TABLE {TABLE} DROP COLUMN {COLUMN};")


def add_column_if_missing(apps, schema_editor):
    if COLUMN not in _columns(schema_editor):
        schema_editor.execute(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} TEXT NOT NULL DEFAULT '';")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_add_log_activite_generique'),
    ]

    operations = [
        migrations.RunPython(drop_column_if_exists, add_column_if_missing),
    ]
