"""
Migration de données : convertit les hospitalisations au statut 'refere'
en 'decharge' avec transfert=True sur leur ResumeDecharge.
"""
from django.db import migrations


def refere_to_decharge(apps, schema_editor):
    Hospitalisation = apps.get_model('hospitalisation', 'Hospitalisation')
    ResumeDecharge  = apps.get_model('hospitalisation', 'ResumeDecharge')

    referes = Hospitalisation.objects.filter(statut='refere')
    for hosp in referes:
        hosp.statut = 'decharge'
        hosp.save(update_fields=['statut'])

        resume, _ = ResumeDecharge.objects.get_or_create(hospitalisation=hosp)
        resume.transfert = True
        resume.save(update_fields=['transfert'])


def decharge_to_refere(apps, schema_editor):
    """Retour arrière : remet les dossiers avec transfert=True en 'refere'."""
    Hospitalisation = apps.get_model('hospitalisation', 'Hospitalisation')
    ResumeDecharge  = apps.get_model('hospitalisation', 'ResumeDecharge')

    for resume in ResumeDecharge.objects.filter(transfert=True):
        hosp = resume.hospitalisation
        if hosp.statut == 'decharge':
            hosp.statut = 'refere'
            hosp.save(update_fields=['statut'])


class Migration(migrations.Migration):

    dependencies = [
        ('hospitalisation', '0027_remove_refere_statut_permission'),
    ]

    operations = [
        migrations.RunPython(refere_to_decharge, decharge_to_refere),
    ]
