from django.db import migrations


CATEGORIES = [
    # Médicaments
    ('Antipaludéens',            'medicament'),
    ('Antibiotiques',            'medicament'),
    ('Antiparasitaires',         'medicament'),
    ('Antifongiques',            'medicament'),
    ('Antiviraux',               'medicament'),
    ('Antidouleurs / Analgésiques', 'medicament'),
    ('Anti-inflammatoires',      'medicament'),
    ('Antihypertenseurs',        'medicament'),
    ('Antidiabétiques',          'medicament'),
    ('Vitamines & Suppléments',  'medicament'),
    ('Contraceptifs',            'medicament'),
    ('Médicaments gynécologie',  'medicament'),
    ('Vaccins',                  'medicament'),
    ('Solutés & Perfusions',     'medicament'),
    ('Produits dermatologiques', 'medicament'),
    ('Ophtalmologiques',         'medicament'),
    ('Médicaments pédiatriques', 'medicament'),
    ('Antitussifs & Expectorants','medicament'),
    ('Antihistaminiques',        'medicament'),
    ('Psychotropes',             'medicament'),
    # Consommables
    ('Pansements & Compresses',  'consommable'),
    ('Seringues & Aiguilles',    'consommable'),
    ('Gants médicaux',           'consommable'),
    ('Masques & Protection',     'consommable'),
    ('Matériel de perfusion',    'consommable'),
    ('Tests de diagnostic rapide','consommable'),
    ('Matériel de prélèvement',  'consommable'),
    ('Désinfectants & Antiseptiques', 'consommable'),
    ('Fils de suture',           'consommable'),
    ('Matériel obstétrique',     'consommable'),
    ('Sondes & Cathéters',       'consommable'),
    ('Produits de laboratoire',  'consommable'),
    # Équipements
    ('Matériel de consultation', 'equipement'),
    ('Matériel de laboratoire',  'equipement'),
    ('Mobilier médical',         'equipement'),
    ('Matériel informatique',    'equipement'),
    ('Électroménager médical',   'equipement'),
    ('Matériel de stérilisation','equipement'),
    ('Imagerie médicale',        'equipement'),
]


def add_categories(apps, schema_editor):
    CategorieStock = apps.get_model('stock', 'CategorieStock')
    for nom, type_ in CATEGORIES:
        CategorieStock.objects.get_or_create(nom=nom, type=type_)


def remove_categories(apps, schema_editor):
    CategorieStock = apps.get_model('stock', 'CategorieStock')
    noms = [n for n, _ in CATEGORIES]
    CategorieStock.objects.filter(nom__in=noms).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('stock', '0001_initial'),
    ]
    operations = [
        migrations.RunPython(add_categories, remove_categories),
    ]
