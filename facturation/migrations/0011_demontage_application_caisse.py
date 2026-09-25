"""Démonte l'application `caisse`, devenue inutile.

Elle ne servait plus qu'à fournir la liste des journaux d'encaissement, repris
par `facturation.Caisse` (migration 0010). Ses deux autres tables, prévues pour
l'ouverture/fermeture de caisse et le suivi des mouvements, n'ont jamais reçu
une seule ligne.

Le ménage est fait ici, et non dans une migration de `caisse` : son dossier
disparaît du dépôt, donc ses migrations ne s'exécuteraient plus chez personne.
Chaque base est nettoyée en migrant, quel que soit son état de départ.
"""

from django.db import migrations

TABLES = ['caisse_transactioncaisse', 'caisse_sessioncaisse', 'caisse_caisse']


def demonter(apps, schema_editor):
    connexion = schema_editor.connection
    presentes = set(connexion.introspection.table_names())
    with connexion.cursor() as cur:
        for table in TABLES:
            if table in presentes:
                cur.execute('DROP TABLE %s' % connexion.ops.quote_name(table))

    # Permissions et types de contenu orphelins : sans ça les anciens libellés
    # anglais restent proposés dans l'écran des groupes.
    ContentType = apps.get_model('contenttypes', 'ContentType')
    types = ContentType.objects.filter(app_label='caisse')
    apps.get_model('auth', 'Permission').objects.filter(content_type__in=types).delete()
    types.delete()

    # L'historique des migrations de l'application supprimée.
    with connexion.cursor() as cur:
        cur.execute("DELETE FROM django_migrations WHERE app = 'caisse'")


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0010_reprise_des_caisses'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        # Irréversible : les tables supprimées ne contenaient rien qu'on sache
        # reconstruire, et `Caisse` vit désormais dans facturation.
        migrations.RunPython(demonter, migrations.RunPython.noop),
    ]
