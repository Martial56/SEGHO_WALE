"""Recopie les caisses de l'application `caisse`, qui disparaît.

Volontairement en SQL brut plutôt qu'avec `apps.get_model('caisse', ...)` :
l'application est supprimée dans la foulée, et une dépendance vers ses
migrations casserait le graphe sur une installation neuve. On lit donc la
table directement, si elle existe encore.

Trois cas, tous gérés :
  • base existante  → les lignes sont reprises ;
  • installation neuve → la table n'existe pas, il n'y a rien à reprendre ;
  • migration rejouée → `code` est unique, `update_or_create` ne double pas.
"""

from django.db import migrations


def _table_existe(schema_editor, nom):
    return nom in schema_editor.connection.introspection.table_names()


def reprendre(apps, schema_editor):
    if not _table_existe(schema_editor, 'caisse_caisse'):
        return
    Caisse = apps.get_model('facturation', 'Caisse')
    with schema_editor.connection.cursor() as cur:
        cur.execute('SELECT nom, code, solde_actuel, responsable_id, actif '
                    'FROM caisse_caisse')
        lignes = cur.fetchall()
    for nom, code, solde, responsable_id, actif in lignes:
        Caisse.objects.update_or_create(
            code=code,
            defaults={
                'nom': nom, 'solde_actuel': solde,
                'responsable_id': responsable_id, 'actif': bool(actif),
            },
        )


def vider(apps, schema_editor):
    """Retour en arrière : la table d'origine n'a jamais été touchée."""
    apps.get_model('facturation', 'Caisse').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0009_caisse'),
    ]

    operations = [
        migrations.RunPython(reprendre, vider),
    ]
