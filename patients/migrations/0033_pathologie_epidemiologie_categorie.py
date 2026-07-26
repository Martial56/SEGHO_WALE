# Recatégorise les maladies à déclaration obligatoire (MDO) du catalogue
# Pathologie en 'epidemiologie', pour piloter une future section du rapport
# mensuel de médecine générale (rapports/med_generale.py) sur le même
# principe que les sections A/B/C (voir 0031_pathologie_med_generale_categories).
#
# Ces 22 libellés sont ceux restés en catégorie 'generale' après 0031 (aucune
# des sections A/B/C du formulaire papier ne les référençait) — voir
# PATHOLOGIES_INITIALES / categorie='declaration' dans 0009_pathologie.py.
from django.db import migrations

NOMS_EPIDEMIOLOGIE = [
    'Choléra cas suspecté', 'Choléra cas investigué',
    'Méningite cas suspecté', 'Méningite cas investigué',
    'Fièvre hémorragique cas suspecté', 'Fièvre hémorragique cas investigué',
    'Paralysie flasque aiguë cas suspecté', 'Paralysie flasque aiguë cas investigué',
    'PFA avec vaccination anti-polio cas', 'PFA avec vaccination anti-polio décès',
    'PFA sans vaccination anti-polio cas', 'PFA sans vaccination anti-polio décès',
    'PFA sans statut vaccinal connu cas', 'PFA sans statut vaccinal connu décès',
    'Peste cas suspecté', 'Peste cas investigué',
    'Diarrhées sanglantes cas suspecté', 'Diarrhées sanglantes cas investigué',
    'Rougeole cas suspecté', 'Rougeole cas investigué',
    'Fièvre jaune cas suspecté', 'Fièvre jaune cas investigué',
]


def recategoriser(apps, schema_editor):
    Pathologie = apps.get_model('patients', 'Pathologie')
    Departement = apps.get_model('medecins', 'Departement')

    medg = (
        Departement.objects.filter(code='medg').first()
        or Departement.objects.filter(code='MEDGEN').first()
    )

    Pathologie.objects.filter(nom__in=NOMS_EPIDEMIOLOGIE).update(
        categorie='epidemiologie', departement=medg,
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0032_alter_pathologie_categorie'),
    ]

    operations = [
        migrations.RunPython(recategoriser, noop_reverse),
    ]
