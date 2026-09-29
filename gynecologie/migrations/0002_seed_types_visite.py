"""Le catalogue des CPN, posé à l'installation de la base.

Sans lui, une base neuve n'a aucun type de visite : la liste déroulante de la
fiche de rendez-vous est vide, `cpn_type_visite` ne peut pas être renseigné, et
le rapport de maternité affiche sept zéros sans qu'on comprenne pourquoi.

Les **codes** ne sont pas décoratifs : `rapports/maternite.py` les cite un par
un pour ventiler les consultations prénatales par rang de visite. Les changer
ici viderait le rapport. Les noms, eux, restent modifiables depuis l'écran de
configuration — ils ne servent qu'à l'affichage.

Même forme que les deux autres catalogues de référence,
`patients/0035_seed_types_visite_curative` et
`medecins/0015_replace_departements_defaut`.
"""
from django.db import migrations

#: (code, nom). Les libellés reprennent les lignes du rapport de maternité,
#: pour qu'on reconnaisse au premier coup d'œil ce que chaque type alimente.
SEED = [
    ('CPN01',  'CPN1 premier trimestre de la grossesse'),
    ('CPNA01', 'CPN1 Autre trimestre de la grossesse'),
    ('CPN02',  'CPN2'),
    ('CPN03',  'CPN3'),
    ('CPNA04', 'CPN4 Autre trimestre de la grossesse'),
    ('CPN04',  'CPN4 au 9ème mois de la grossesse'),
    ('CPN05',  'CPN5 et plus'),
]


def seed(apps, schema_editor):
    """Pose ce qui manque, sans toucher à ce qui existe.

    `get_or_create` et non `update_or_create` : sur une base déjà en service,
    un nom retouché depuis l'écran de configuration doit le rester.
    """
    TypeVisite = apps.get_model('gynecologie', 'TypeVisite')
    for code, nom in SEED:
        TypeVisite.objects.get_or_create(code=code, defaults={'nom': nom, 'actif': True})


def unseed(apps, schema_editor):
    TypeVisite = apps.get_model('gynecologie', 'TypeVisite')
    TypeVisite.objects.filter(code__in=[code for code, _ in SEED]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('gynecologie', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
