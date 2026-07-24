from django.db import migrations


def migrer_signataires(apps, schema_editor):
    PlanningHebdomadaire = apps.get_model('planning', 'PlanningHebdomadaire')
    PlanningConfig = apps.get_model('planning', 'PlanningConfig')
    MedecinSignataire = apps.get_model('planning', 'MedecinSignataire')

    cache = {}

    def get_medecin(nom):
        nom = (nom or '').strip()
        if not nom:
            return None
        if nom not in cache:
            cache[nom], _ = MedecinSignataire.objects.get_or_create(nom=nom)
        return cache[nom]

    for planning in PlanningHebdomadaire.objects.exclude(signataire='').only('id', 'signataire'):
        planning.signataire_new = get_medecin(planning.signataire)
        planning.save(update_fields=['signataire_new'])

    config = PlanningConfig.objects.first()
    if config and config.signataire_defaut:
        config.medecin_defaut = get_medecin(config.signataire_defaut)
        config.save(update_fields=['medecin_defaut'])


def revenir_arriere(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0010_medecin_signataire'),
    ]

    operations = [
        migrations.RunPython(migrer_signataires, revenir_arriere),
    ]
