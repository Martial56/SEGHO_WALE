from django.db import migrations

MODULES = [
    {'code': 'patients',       'name': 'Patients',       'icon': '🏥', 'url_name': 'patients:list',            'order': 1},
    {'code': 'rendezvous',     'name': 'Rendez-vous',    'icon': '📅', 'url_name': 'patients:rdv_global',      'order': 2},
    {'code': 'soins',          'name': 'Soins',          'icon': '💉', 'url_name': 'soins:list',               'order': 3},
    {'code': 'medicaments',    'name': 'Médicaments',    'icon': '💊', 'url_name': 'medicament:list',          'order': 4},
    {'code': 'pharmacie',      'name': 'Pharmacie',      'icon': '⚕️', 'url_name': '',                        'order': 5},
    {'code': 'ordonnances',    'name': 'Ordonnances',    'icon': '📋', 'url_name': '',                        'order': 6},
    {'code': 'laboratoire',    'name': 'Laboratoire',    'icon': '🔬', 'url_name': 'laboratoire_list',        'order': 7},
    {'code': 'hospitalisation','name': 'Hospitalisation','icon': '🛏️', 'url_name': 'hospitalisation_list',    'order': 8},
    {'code': 'gynecologie',    'name': 'Gynécologie',    'icon': '🩺', 'url_name': '',                        'order': 9},
    {'code': 'facturation',    'name': 'Comptabilité',   'icon': '💰', 'url_name': 'facturation_list',        'order': 10},
    {'code': 'assurance',      'name': 'Assurance',      'icon': '🛡️', 'url_name': '',                       'order': 11},
    {'code': 'achats',         'name': 'Achats',         'icon': '🛒', 'url_name': '',                        'order': 12},
    {'code': 'stock',          'name': 'Stock',          'icon': '📦', 'url_name': '',                        'order': 13},
    {'code': 'planning',       'name': 'Planning',       'icon': '🗓️', 'url_name': '',                       'order': 14},
    {'code': 'employer',       'name': 'Employés',       'icon': '👔', 'url_name': 'employer:ressources_humaines_list', 'order': 15},
    {'code': 'conges',         'name': 'Congés',         'icon': '🏖️', 'url_name': '',                       'order': 16},
    {'code': 'presence',       'name': 'Présence',       'icon': '📊', 'url_name': '',                        'order': 17},
    {'code': 'services',       'name': 'Prestations',    'icon': '🏷️', 'url_name': '',                       'order': 18},
    {'code': 'utilisateur',    'name': 'Utilisateurs',   'icon': '👤', 'url_name': 'utilisateur:list',        'order': 19},
    {'code': 'admin',          'name': 'Administration', 'icon': '⚙️', 'url_name': '',                       'order': 20},
]


def populate(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    for m in MODULES:
        Module.objects.get_or_create(code=m['code'], defaults={
            'name':     m['name'],
            'icon':     m['icon'],
            'url_name': m['url_name'],
            'order':    m['order'],
            'is_active': True,
        })


def depopulate(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    Module.objects.filter(code__in=[m['code'] for m in MODULES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('modules_permissions', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(populate, depopulate),
    ]
