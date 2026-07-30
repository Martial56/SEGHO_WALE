from django.db import migrations

# Nouvelle entrée du menu Configurations des rendez-vous : les types de visite
# curative, qui étaient auparavant trois valeurs écrites en dur dans le
# formulaire. Ajoutée ici pour rester masquable par groupe depuis /admin/.
CODE = 'patients.typevisitecurative_config'
LABEL = "Configurations (Type de visite curative)"
MODULE_CODE = 'rendezvous'


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
        ('modules_permissions', '0007_populate_navitems'),
    ]

    operations = [
        migrations.RunPython(ajouter, retirer),
    ]
