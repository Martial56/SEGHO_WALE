from django.db import migrations

FONCTIONS_SUP = [
    ('Opérateur(rice) de Saisie',       'OP-SAISIE'),
    ('Gestionnaire de Projet',           'GEST-PROJ'),
    ('Gestionnaire de Projet Adjoint',   'GEST-PROJ-ADJ'),
    ('AMD',                              'AMD'),
    ('Conseiller(ère) Communautaire',    'CONS-COM'),
    ('Technicien(ne) de Surface',        'TECH-SURF'),
    ('Gardien',                          'GARDIEN'),
    ('Chargé(e) de Commande',           'CHARG-CMD'),
    ('Auxiliaire en Pharmacie',          'AUX-PHAR'),
]


def ajouter(apps, schema_editor):
    Fonction = apps.get_model('employer', 'Fonction')
    for nom, code in FONCTIONS_SUP:
        Fonction.objects.get_or_create(code=code, defaults={'nom': nom})


def supprimer(apps, schema_editor):
    Fonction = apps.get_model('employer', 'Fonction')
    codes = [c for _, c in FONCTIONS_SUP]
    Fonction.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0015_fonctions_initiales'),
    ]

    operations = [
        migrations.RunPython(ajouter, supprimer),
    ]
