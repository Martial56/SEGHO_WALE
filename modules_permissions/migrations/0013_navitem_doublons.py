"""L'entrée « Doublons » du module Patients.

Comme les autres : masquable par groupe ou par utilisateur depuis /admin/. La
permission `patients.gerer_doublons` reste le premier filtre — le NavItem ne
fait que cacher un lien, il n'autorise rien.
"""

from django.db import migrations

CODE = 'patients.doublons'
LABEL = 'Doublons'
MODULE_CODE = 'patients'


def ajouter(apps, schema_editor):
    NavItem = apps.get_model('modules_permissions', 'NavItem')
    Module = apps.get_model('modules_permissions', 'Module')
    module = Module.objects.filter(code=MODULE_CODE).first()
    NavItem.objects.get_or_create(code=CODE, defaults={'label': LABEL, 'module': module})


def retirer(apps, schema_editor):
    NavItem = apps.get_model('modules_permissions', 'NavItem')
    NavItem.objects.filter(code=CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('modules_permissions', '0012_navitem_facturation_config_presence_biometrie'),
    ]

    operations = [
        migrations.RunPython(ajouter, retirer),
    ]
