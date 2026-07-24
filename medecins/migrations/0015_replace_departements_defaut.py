from django.db import migrations

# Remplace les 3 départements auto-créés par la migration 0009 (Médical,
# Administratif et Logistique, Soins et Prise en Charge) par les 2
# départements réellement utilisés par l'application (le circuit gynéco
# — menu, RDV, ordonnances, rapports — filtre sur Departement.code == 'GYN',
# qu'aucune migration ne créait jusqu'ici).
#
# Service.departement est en SET_NULL : les services déjà rattachés aux
# anciens départements (migration 0009/0010) sont détachés proprement,
# pas supprimés.

ANCIENS_CODES = ['DEPT-MED', 'DEPT-ADMIN', 'DEPT-SOINS']

NOUVEAUX = [
    ('MEDGEN', 'Médecine Générale'),
    ('GYN',    'Gynécologie'),
]


def remplacer(apps, schema_editor):
    Departement = apps.get_model('medecins', 'Departement')
    Departement.objects.filter(code__in=ANCIENS_CODES).delete()
    for code, nom in NOUVEAUX:
        Departement.objects.get_or_create(code=code, defaults={'nom': nom})


def restaurer(apps, schema_editor):
    Departement = apps.get_model('medecins', 'Departement')
    Departement.objects.filter(code__in=[c for c, _ in NOUVEAUX]).delete()
    for code, nom in [
        ('DEPT-MED', 'Département Médical'),
        ('DEPT-ADMIN', 'Département Administratif et Logistique'),
        ('DEPT-SOINS', 'Département Soins et Prise en Charge'),
    ]:
        Departement.objects.get_or_create(code=code, defaults={'nom': nom})


class Migration(migrations.Migration):

    dependencies = [
        ('medecins', '0014_delete_modulespecialise'),
    ]

    operations = [
        migrations.RunPython(remplacer, restaurer),
    ]
