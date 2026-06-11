"""
Réconciliation du schéma JourFerie : la table a été créée par 0024_sync_legacy_schema
avec les colonnes nom/recurrent, mais le modèle utilise description.
Cette migration aligne la DB sur le modèle actuel via SQL brut (SQLite).
"""
from django.db import migrations


def add_description_column(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        # Vérifier si description existe déjà
        cursor.execute("PRAGMA table_info(ressources_humaines_jourferie)")
        cols = [row[1] for row in cursor.fetchall()]
        if 'description' not in cols:
            cursor.execute(
                'ALTER TABLE "ressources_humaines_jourferie" '
                'ADD COLUMN "description" varchar(100) NOT NULL DEFAULT \'\''
            )
            # Migrer les données de nom vers description si nom existe
            if 'nom' in cols:
                cursor.execute(
                    'UPDATE "ressources_humaines_jourferie" '
                    'SET description = nom WHERE description = \'\''
                )


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0024_sync_legacy_schema'),
    ]

    operations = [
        migrations.RunPython(add_description_column, reverse_code=migrations.RunPython.noop),
    ]
