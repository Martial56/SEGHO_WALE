from django.db import migrations

UNITES = [
    # (nom, code, categorie)
    ('Comprimé',       'cp',    'Médicaments'),
    ('Gélule',         'gel',   'Médicaments'),
    ('Ampoule',        'amp',   'Médicaments'),
    ('Flacon',         'fl',    'Médicaments'),
    ('Sachet',         'sach',  'Médicaments'),
    ('Tube',           'tube',  'Médicaments'),
    ('Suppositoire',   'supp',  'Médicaments'),
    ('Poche',          'poche', 'Médicaments'),
    ('Boîte',          'boîte', 'Médicaments'),
    ('Pièce',          'pce',   'Consommables'),
    ('Paire',          'paire', 'Consommables'),
    ('Rouleau',        'roul',  'Consommables'),
    ('Litre',          'L',     'Consommables'),
    ('Millilitre',     'ml',    'Consommables'),
    ('Kilogramme',     'kg',    'Consommables'),
    ('Gramme',         'g',     'Consommables'),
    ('Unité',          'u',     'Équipements'),
    ('Lot',            'lot',   'Équipements'),
    ('Set / Kit',      'set',   'Équipements'),
]


def seed_unites(apps, schema_editor):
    UniteMesure = apps.get_model('stock', 'UniteMesure')
    for nom, code, categorie in UNITES:
        UniteMesure.objects.get_or_create(
            code=code,
            defaults={'nom': nom, 'categorie': categorie, 'actif': True},
        )


def unseed_unites(apps, schema_editor):
    pass  # on ne supprime pas en rollback


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0015_alter_unitemesure_categorie'),
    ]

    operations = [
        migrations.RunPython(seed_unites, unseed_unites),
    ]
