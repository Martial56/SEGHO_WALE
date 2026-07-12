from django.db import migrations

SERVICES = [
    ('Prise en Charge',       'PRISE-CHARGE'),
    ('Maternité',             'MATERNITE'),
    ('Soins et Infirmerie',   'SOINS-INF'),
    ('Imagerie',              'IMAGERIE'),
    ('Sécurité',              'SECURITE'),
    ('Nettoyage',             'NETTOYAGE'),
]


def ajouter(apps, schema_editor):
    Service = apps.get_model('medecins', 'Service')
    for nom, code in SERVICES:
        Service.objects.get_or_create(code=code, defaults={'nom': nom, 'actif': True})


def supprimer(apps, schema_editor):
    Service = apps.get_model('medecins', 'Service')
    Service.objects.filter(code__in=[c for _, c in SERVICES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('medecins', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(ajouter, supprimer),
    ]
