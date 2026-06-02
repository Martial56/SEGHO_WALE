from django.db import migrations

DEFAULT_MODULES = [
    {'code': 'patients',            'name': 'Patients',            'icon': '👥', 'url_name': 'patients_list',            'order': 1},
    {'code': 'medecins',            'name': 'Médecins',            'icon': '👨‍⚕️', 'url_name': 'medecins_list',            'order': 2},
    {'code': 'consultations',       'name': 'Consultations',       'icon': '💊', 'url_name': 'consultations_list',       'order': 3},
    {'code': 'pharmacie',           'name': 'Pharmacie',           'icon': '⚗️', 'url_name': 'pharmacie_list',           'order': 4},
    {'code': 'laboratoire',         'name': 'Laboratoire',         'icon': '🧪', 'url_name': 'laboratoire_list',         'order': 5},
    {'code': 'hospitalisation',     'name': 'Hospitalisation',     'icon': '🛏️', 'url_name': 'hospitalisation_list',     'order': 6},
    {'code': 'facturation',         'name': 'Facturation',         'icon': '💰', 'url_name': 'facturation_list',         'order': 7},
    {'code': 'caisse',              'name': 'Caisse',              'icon': '💵', 'url_name': 'caisse_list',              'order': 8},
    {'code': 'ressources_humaines', 'name': 'Ressources Humaines', 'icon': '👤', 'url_name': 'ressources_humaines_list', 'order': 9},
    {'code': 'rapports',            'name': 'Rapports',            'icon': '📋', 'url_name': 'rapports_list',            'order': 10},
    {'code': 'admin',               'name': 'Administration',      'icon': '⚙️', 'url_name': '',                         'order': 11},
]

def populate_modules(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    for m in DEFAULT_MODULES:
        Module.objects.get_or_create(code=m['code'], defaults=m)

def unpopulate_modules(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    Module.objects.filter(code__in=[m['code'] for m in DEFAULT_MODULES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('modules_permissions', '0001_initial'),
    ]
    operations = [
        migrations.RunPython(populate_modules, unpopulate_modules),
    ]
