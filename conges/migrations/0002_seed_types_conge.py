from django.db import migrations

SEED = [
    # code,               nom,                          couleur,  deductible, duree_forfaitaire, ordre
    ('annuel',           'Congé annuel',                'green', True,  None, 0),
    ('maladie',          'Congé maladie',               'amber', False, None, 1),
    ('maternite',        'Congé maternité',             'pink',  False, 98,   2),
    ('paternite',        'Congé paternité',             'pink',  True,  3,    3),
    ('exceptionnel',     'Congé exceptionnel',          'blue',  True,  None, 4),
    ('mariage_employe',  'Mariage (employé)',           'blue',  True,  5,    5),
    ('mariage_enfant',   'Mariage (enfant)',            'blue',  True,  2,    6),
    ('deces_conjoint',   'Décès conjoint',               'gray',  True,  5,    7),
    ('deces_enfant',     'Décès enfant',                 'gray',  True,  5,    8),
    ('deces_parent',     'Décès parent/beau-parent',    'gray',  True,  3,    9),
    ('deces_frere_soeur','Décès frère/sœur',            'gray',  True,  2,    10),
    ('naissance_enfant', 'Naissance enfant (père)',      'blue',  True,  3,    11),
    ('sans_solde',       'Congé sans solde',            'gray',  False, None, 12),
]


def seed(apps, schema_editor):
    TypeConge = apps.get_model('conges', 'TypeConge')
    for code, nom, couleur, deductible, duree, ordre in SEED:
        TypeConge.objects.get_or_create(code=code, defaults={
            'nom': nom, 'couleur': couleur, 'deductible': deductible,
            'duree_forfaitaire': duree, 'ordre': ordre, 'actif': True,
        })


def unseed(apps, schema_editor):
    TypeConge = apps.get_model('conges', 'TypeConge')
    TypeConge.objects.filter(code__in=[row[0] for row in SEED]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('conges', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
