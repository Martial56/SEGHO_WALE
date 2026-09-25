from django.db import migrations

# « Diagnostic retenu » a été déplacé dans la branche Rendez-vous de la barre de
# navigation (voir le commentaire de templates/patients/includes/nav.html), mais
# son entrée de menu était restée rattachée au module « patients » depuis la
# migration 0007. Conséquence : la case n'apparaissait pas dans la checklist des
# groupes n'ayant que le module « rendezvous », on ne pouvait donc pas la
# masquer, et comme le menu « Configurations » s'affiche dès qu'un de ses deux
# enfants est visible, décocher « Type de visite curative » ne suffisait pas à
# le faire disparaître.
CODE = 'patients.pathologie_config'
ANCIEN_MODULE = 'patients'
NOUVEAU_MODULE = 'rendezvous'


def _deplacer(apps, vers):
    NavItem = apps.get_model('modules_permissions', 'NavItem')
    Module = apps.get_model('modules_permissions', 'Module')
    module = Module.objects.filter(code=vers).first()
    if module is None:
        return
    NavItem.objects.filter(code=CODE).update(module=module)


def vers_rendezvous(apps, schema_editor):
    _deplacer(apps, NOUVEAU_MODULE)


def vers_patients(apps, schema_editor):
    _deplacer(apps, ANCIEN_MODULE)


class Migration(migrations.Migration):

    dependencies = [
        ('modules_permissions', '0008_navitem_typevisite_curative'),
    ]

    operations = [
        migrations.RunPython(vers_rendezvous, vers_patients),
    ]
