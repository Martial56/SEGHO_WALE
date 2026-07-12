from django.db import migrations


CODE_MAP = {
    'medecine_generale': 'MED-GEN',
    'gynecologie_cpn': 'GYNECO',
}


def migrate_departement_data(apps, schema_editor):
    RendezVous = apps.get_model('patients', 'RendezVous')
    Service = apps.get_model('medecins', 'Service')
    services = {s.code: s for s in Service.objects.all()}
    for rdv in RendezVous.objects.exclude(departement_code_old=''):
        service_code = CODE_MAP.get(rdv.departement_code_old)
        service = services.get(service_code) if service_code else None
        if service:
            rdv.departement_id = service.pk
            rdv.save(update_fields=['departement'])


def reverse_migrate_departement_data(apps, schema_editor):
    RendezVous = apps.get_model('patients', 'RendezVous')
    reverse_map = {v: k for k, v in CODE_MAP.items()}
    for rdv in RendezVous.objects.exclude(departement__isnull=True):
        code = reverse_map.get(rdv.departement.code)
        if code:
            rdv.departement_code_old = code
            rdv.save(update_fields=['departement_code_old'])


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0018_rendezvous_departement_service_step1'),
    ]

    operations = [
        migrations.RunPython(migrate_departement_data, reverse_migrate_departement_data),
    ]
