from django.db import migrations

# Le module Comptabilité se scinde : « Caisse » (Ma caisse, Factures, Journées
# de caisse) et « Comptabilité » (tout le reste). Le module Caisse reprend le
# code `caisse`, semé en 0002 pour une application jamais construite.
#
# Personne ne perd d'accès : tout groupe, tout utilisateur qui avait le
# module Comptabilité (code `facturation`) reçoit aussi le module Caisse. On
# retire ensuite, dans l'admin, la Comptabilité aux caissières.
CAISSE = ['comptabilite.caisse', 'facturation.list', 'comptabilite.journees']
NOUVEAU = ('comptabilite.documents_ventes', 'Documents des ventes')


def poser(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    GroupModule = apps.get_model('modules_permissions', 'GroupModule')
    UserModuleOverride = apps.get_model('modules_permissions', 'UserModuleOverride')
    NavItem = apps.get_model('modules_permissions', 'NavItem')

    caisse, _ = Module.objects.update_or_create(code='caisse', defaults={
        'name': 'Caisse', 'icon': '💵', 'url_name': 'facturation:list', 'order': 2, 'is_active': True,
        'description': "Session de la caissière, factures et journées de caisse."})
    compta = Module.objects.filter(code='facturation').first()
    if compta is None:
        return
    compta.url_name = 'comptabilite:accueil'
    compta.save(update_fields=['url_name'])
    for gm in GroupModule.objects.filter(module=compta):
        GroupModule.objects.get_or_create(group_id=gm.group_id, module=caisse)
    for o in UserModuleOverride.objects.filter(module=compta):
        UserModuleOverride.objects.get_or_create(user_id=o.user_id, module=caisse,
                                                 defaults={'override_type': o.override_type})
    NavItem.objects.filter(code__in=CAISSE).update(module=caisse)
    NavItem.objects.update_or_create(code=NOUVEAU[0], defaults={'label': NOUVEAU[1], 'module': compta})


def retirer(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    NavItem = apps.get_model('modules_permissions', 'NavItem')
    compta = Module.objects.filter(code='facturation').first()
    NavItem.objects.filter(code__in=CAISSE).update(module=compta)
    NavItem.objects.filter(code=NOUVEAU[0]).delete()
    Module.objects.filter(code='facturation').update(url_name='facturation:list')
    Module.objects.filter(code='caisse').update(name='Caisse', url_name='caisse_list', order=16)


class Migration(migrations.Migration):

    dependencies = [
        ('modules_permissions', '0021_navitem_achats'),
    ]

    operations = [
        migrations.RunPython(poser, retirer),
    ]
