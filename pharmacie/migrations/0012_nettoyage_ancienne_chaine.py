"""Retire les traces que la suppression des modèles laisse derrière elle.

Supprimer un modèle vide sa table, mais laisse son `ContentType` et les quatre
permissions qui s'y rattachent : elles continueraient d'apparaître dans la liste
des droits de l'admin, à côté de celles du modèle `stock.MouvementStock` qui
porte le même nom — on ne saurait plus laquelle cocher.

Aucune de ces seize permissions n'est attribuée à qui que ce soit, ni à un
utilisateur ni à un groupe : le nettoyage ne retire de droit à personne. La
migration le vérifie tout de même avant de supprimer, plutôt que de s'en
remettre à ce constat daté.
"""

from django.db import migrations


#: Modèles de l'ancienne chaîne pharmacie, supprimés par la migration 0011.
MODELES_SUPPRIMES = ('medicament', 'lotmedicament', 'mouvementstock',
                     'categoriemedicament')


def nettoyer(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')

    types = ContentType.objects.filter(
        app_label='pharmacie', model__in=MODELES_SUPPRIMES)
    permissions = Permission.objects.filter(content_type__in=types)

    # Une permission encore attribuée signale que le modèle servait à quelqu'un :
    # on la laisse en place plutôt que de retirer un droit sans le dire.
    attribuees = set(
        permissions.filter(group__isnull=False).values_list('pk', flat=True)
    ) | set(
        permissions.filter(user__isnull=False).values_list('pk', flat=True)
    )
    permissions.exclude(pk__in=attribuees).delete()
    if not attribuees:
        types.delete()


def ne_rien_faire(apps, schema_editor):
    """Rien à remonter : Django recrée ces lignes si les modèles reviennent."""


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacie', '0011_remove_medicament_categorie_and_more'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(nettoyer, ne_rien_faire),
    ]
