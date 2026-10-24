from django.db import migrations

# Le module Facturation devient « Comptabilité » : la facturation en est un
# sous-menu, à côté des sessions de caisse. Le **code** reste `facturation` :
# c'est lui que portent les attributions aux groupes, les verrous
# `module_requis` et les gabarits. Seul le libellé change, et aucun groupe ne
# perd l'accès qu'il avait.
#
# Les deux nouvelles entrées de menu reçoivent leur ligne NavItem, sans quoi
# elles n'apparaîtraient pas dans la checklist de l'admin et ne pourraient pas
# être retirées à un groupe (voir 0012).
NOUVEAUX = [
    ('comptabilite.caisse', 'Ma caisse'),
    ('comptabilite.journees', 'Journées de caisse'),
]


def poser(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    NavItem = apps.get_model('modules_permissions', 'NavItem')
    Module.objects.filter(code='facturation').update(name='Comptabilité')
    module = Module.objects.filter(code='facturation').first()
    for code, label in NOUVEAUX:
        NavItem.objects.update_or_create(code=code, defaults={'label': label, 'module': module})


def retirer(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    NavItem = apps.get_model('modules_permissions', 'NavItem')
    Module.objects.filter(code='facturation').update(name='Facturation')
    NavItem.objects.filter(code__in=[c for c, _ in NOUVEAUX]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('modules_permissions', '0013_navitem_doublons'),
    ]

    operations = [
        migrations.RunPython(poser, retirer),
    ]
