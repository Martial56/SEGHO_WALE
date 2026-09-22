from django.db import migrations

# Les deux onglets du module Soins (« Soins infirmiers », « Liste des soins »)
# n'avaient pas de module parent. Or la checklist des menus d'un groupe ne
# présente que les entrées rattachées à un module — voir le filtre `if module`
# de modules_permissions.admin.GroupAdminWithModules.group_navitems_view. Sans
# parent, ces deux cases n'apparaissaient nulle part et ces onglets étaient donc
# impossibles à masquer, pour n'importe quel groupe.
#
# Le module auquel ils appartiennent est « consultations » : c'est sa carte du
# tableau de bord, intitulée « Soins », qui mène à ces pages
# (templates/core/dashboard.html, `'consultations' in accessible_codes` →
# soins:list).
CODES = ['soins.list', 'soins.procedures']
MODULE_CODE = 'consultations'


def rattacher(apps, schema_editor):
    NavItem = apps.get_model('modules_permissions', 'NavItem')
    Module = apps.get_model('modules_permissions', 'Module')
    module = Module.objects.filter(code=MODULE_CODE).first()
    if module is None:
        return
    NavItem.objects.filter(code__in=CODES).update(module=module)


def detacher(apps, schema_editor):
    NavItem = apps.get_model('modules_permissions', 'NavItem')
    NavItem.objects.filter(code__in=CODES).update(module=None)


class Migration(migrations.Migration):

    dependencies = [
        ('modules_permissions', '0009_navitem_pathologie_config_rendezvous'),
    ]

    operations = [
        migrations.RunPython(rattacher, detacher),
    ]
