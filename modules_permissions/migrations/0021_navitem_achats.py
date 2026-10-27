from django.db import migrations

# Le menu « Achats » du module Comptabilité (lot 8) reçoit sa ligne NavItem,
# pour pouvoir être retiré à un groupe dans l'admin (voir 0012 et suivantes).
CODE, LIBELLE = 'comptabilite.achats', 'Achats'


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
        ('modules_permissions', '0020_navitem_tresorerie'),
    ]

    operations = [
        migrations.RunPython(poser, retirer),
    ]
