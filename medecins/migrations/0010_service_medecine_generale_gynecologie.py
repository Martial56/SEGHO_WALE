from django.db import migrations


SERVICES = [
    ('MED-GEN', 'Médecine Générale'),
    ('GYNECO',  'Gynécologie'),
]


def ajouter(apps, schema_editor):
    Service = apps.get_model('medecins', 'Service')
    Departement = apps.get_model('medecins', 'Departement')
    dept_medical = Departement.objects.filter(code='DEPT-MED').first()
    for code, nom in SERVICES:
        Service.objects.get_or_create(
            code=code, defaults={'nom': nom, 'actif': True, 'departement': dept_medical}
        )


def supprimer(apps, schema_editor):
    Service = apps.get_model('medecins', 'Service')
    Service.objects.filter(code__in=[c for c, _ in SERVICES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('medecins', '0009_service_departement'),
    ]

    operations = [
        migrations.RunPython(ajouter, supprimer),
    ]
