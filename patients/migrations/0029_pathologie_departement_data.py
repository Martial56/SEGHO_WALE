from django.db import migrations

# Codes confirmés en base réelle (voir Departement.objects.values('code', 'nom')) :
# 'medg' est le département "Médecine générale" réellement utilisé par les
# médecins/rendez-vous existants. 'MEDGEN' est un doublon orphelin créé par
# medecins.0015_replace_departements_defaut (get_or_create sur un code qui ne
# correspondait pas au code réel) — ne pas l'utiliser ici.
CATEGORIE_TO_DEPARTEMENT_CODE = {
    'generale': 'medg',
    'gynecologie': 'GYN',
}


def backfill_departement(apps, schema_editor):
    Pathologie = apps.get_model('patients', 'Pathologie')
    Departement = apps.get_model('medecins', 'Departement')

    for categorie, code in CATEGORIE_TO_DEPARTEMENT_CODE.items():
        departement = Departement.objects.filter(code=code).first()
        if departement:
            Pathologie.objects.filter(categorie=categorie, departement__isnull=True).update(departement=departement)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0028_pathologie_departement'),
    ]

    operations = [
        migrations.RunPython(backfill_departement, noop_reverse),
    ]
