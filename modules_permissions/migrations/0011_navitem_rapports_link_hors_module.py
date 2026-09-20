from django.db import migrations

# « Rapports » de la barre du tableau de bord (core/includes/nav.html, à côté de
# « Vue d'ensemble ») était rattaché au module « rapports ». Deux conséquences :
#
# * la case n'apparaissait que pour les groupes possédant ce module, alors que le
#   lien, lui, s'affiche pour tout le monde — la barre du tableau de bord ne
#   teste que hidden_navitem_codes, jamais l'appartenance au module ;
# * elle se confondait avec `rapports.hub`, l'onglet du module Rapports, qui
#   porte le même libellé mais vit dans une autre barre.
#
# Ce lien appartient à la barre du tableau de bord, qui n'est le menu d'aucun
# module : comme `core.kpi_dashboard` son voisin, il va donc dans la section
# « Général » de la checklist.
CODE = 'core.rapports_link'
ANCIEN_MODULE = 'rapports'


def hors_module(apps, schema_editor):
    NavItem = apps.get_model('modules_permissions', 'NavItem')
    NavItem.objects.filter(code=CODE).update(module=None)


def vers_rapports(apps, schema_editor):
    NavItem = apps.get_model('modules_permissions', 'NavItem')
    Module = apps.get_model('modules_permissions', 'Module')
    module = Module.objects.filter(code=ANCIEN_MODULE).first()
    if module is not None:
        NavItem.objects.filter(code=CODE).update(module=module)


class Migration(migrations.Migration):

    dependencies = [
        ('modules_permissions', '0010_navitem_soins_module_consultations'),
    ]

    operations = [
        migrations.RunPython(hors_module, vers_rapports),
    ]
