import django.db.models.deletion
from django.db import migrations, models


DEPARTEMENTS = [
    ('DEPT-MED', 'Département Médical'),
    ('DEPT-ADMIN', 'Département Administratif et Logistique'),
    ('DEPT-SOINS', 'Département Soins et Prise en Charge'),
]

SERVICE_TO_DEPARTEMENT = {
    'MATERNITE':    'DEPT-MED',
    'IMAGERIE':     'DEPT-MED',
    'ADMIN':        'DEPT-ADMIN',
    'SECURITE':     'DEPT-ADMIN',
    'NETTOYAGE':    'DEPT-ADMIN',
    'SOINS-INF':    'DEPT-SOINS',
    'PRISE-CHARGE': 'DEPT-SOINS',
}


def seed_and_assign(apps, schema_editor):
    Departement = apps.get_model('medecins', 'Departement')
    Service = apps.get_model('medecins', 'Service')

    departements = {}
    for code, nom in DEPARTEMENTS:
        dept, _ = Departement.objects.get_or_create(code=code, defaults={'nom': nom})
        departements[code] = dept

    for service in Service.objects.all():
        dept_code = SERVICE_TO_DEPARTEMENT.get(service.code)
        if dept_code:
            service.departement = departements[dept_code]
            service.save(update_fields=['departement'])


def reverse_seed_and_assign(apps, schema_editor):
    Departement = apps.get_model('medecins', 'Departement')
    Service = apps.get_model('medecins', 'Service')
    Service.objects.update(departement=None)
    Departement.objects.filter(code__in=[c for c, _ in DEPARTEMENTS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('medecins', '0008_medecin_employe_alter_medecin_specialite'),
    ]

    operations = [
        migrations.AddField(
            model_name='service',
            name='departement',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='services', to='medecins.departement'),
        ),
        migrations.RunPython(seed_and_assign, reverse_seed_and_assign),
    ]
