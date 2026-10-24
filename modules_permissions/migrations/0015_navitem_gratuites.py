from django.db import migrations

# Le menu « Gratuités » du module Comptabilité reçoit sa ligne NavItem, pour
# pouvoir être retiré à un groupe dans l'admin (voir 0012 et 0014).
CODE, LIBELLE = 'comptabilite.gratuites', 'Gratuités'


def poser(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    NavItem = apps.get_model('modules_permissions', 'NavItem')
    NavItem.objects.update_or_create(
        code=CODE, defaults={'label': LIBELLE,
                             'module': Module.objects.filter(code='facturation').first()})


def retirer(apps, schema_editor):
    apps.get_model('modules_permissions', 'NavItem').objects.filter(code=CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('modules_permissions', '0014_module_comptabilite'),
    ]

    operations = [
        migrations.RunPython(poser, retirer),
    ]
