from django.db import migrations

NEW_MODULES = [
    {'code': 'rendezvous',  'name': 'Rendez-vous',  'icon': '📅', 'url_name': 'admin:patients_rendezvous_changelist',                    'order':  2},
    {'code': 'assurance',   'name': 'Assurance',    'icon': '🛡️', 'url_name': 'admin:patients_assurance_changelist',                     'order':  3},
    {'code': 'services',    'name': 'Services',     'icon': '🏥', 'url_name': 'admin:medecins_service_changelist',                       'order':  5},
    {'code': 'ordonnances', 'name': 'Ordonnances',  'icon': '📋', 'url_name': 'admin:consultations_ordonnance_changelist',               'order':  7},
    {'code': 'gynecologie', 'name': 'Gynécologie',  'icon': '♀️', 'url_name': 'admin:consultations_consultation_changelist',            'order':  8},
    {'code': 'medicaments', 'name': 'Médicaments',  'icon': '💊', 'url_name': 'admin:pharmacie_medicament_changelist',                   'order': 12},
    {'code': 'stock',       'name': 'Stock',        'icon': '📦', 'url_name': 'admin:pharmacie_lotmedicament_changelist',                'order': 13},
    {'code': 'achats',      'name': 'Achats',       'icon': '🛒', 'url_name': 'admin:pharmacie_commandepharmacies_changelist',           'order': 14},
    {'code': 'planning',    'name': 'Planning',     'icon': '🗓️', 'url_name': 'admin:patients_rendezvous_changelist',                    'order': 18},
    {'code': 'evaluation',  'name': 'Évaluation',   'icon': '⭐', 'url_name': 'admin:ressources_humaines_evaluationemploye_changelist',  'order': 19},
    {'code': 'presence',    'name': 'Présence',     'icon': '✅', 'url_name': 'admin:ressources_humaines_presence_changelist',           'order': 20},
    {'code': 'conges',      'name': 'Congés',       'icon': '🏖️', 'url_name': 'admin:ressources_humaines_conge_changelist',              'order': 21},
]

# Corrections sur les modules existants (noms, icônes, url_name)
UPDATES = [
    {'code': 'patients',            'icon': '👤',  'url_name': 'patients:list',          'order':  1},
    {'code': 'medecins',            'name': 'Médecins',                                   'order':  4},
    {'code': 'consultations',       'name': 'Soins',    'icon': '🩺',                     'order':  6},
    {'code': 'laboratoire',         'icon': '🔬',                                          'order': 10},
    {'code': 'pharmacie',           'icon': '⚕️',                                          'order': 11},
    {'code': 'facturation',         'name': 'Comptabilité', 'icon': '📊',                 'order': 15},
    {'code': 'caisse',              'order': 16},
    {'code': 'ressources_humaines', 'name': 'Employés',  'icon': '👥',                    'order': 17},
    {'code': 'rapports',            'order': 22},
    {'code': 'admin',               'name': 'Paramètres', 'url_name': 'admin:index',      'order': 23},
]


def apply(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')

    for m in NEW_MODULES:
        Module.objects.get_or_create(code=m['code'], defaults=m)

    for upd in UPDATES:
        code = upd.pop('code')
        Module.objects.filter(code=code).update(**upd)


def revert(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    Module.objects.filter(code__in=[m['code'] for m in NEW_MODULES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('modules_permissions', '0002_populate_modules'),
    ]
    operations = [
        migrations.RunPython(apply, revert),
    ]
