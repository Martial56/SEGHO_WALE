from django.db import migrations

# Motifs de départ, pour que les écrans servent dès la mise en service. Ils se
# renomment, se désactivent et se complètent dans Comptabilité → Configuration.
# Les plafonds de remise sont laissés à 100 % : c'est à la direction de les
# fixer, pas au logiciel de les deviner.
MOTIFS_SORTIE = [
    'Achat de fournitures',
    'Transport / course',
    'Petit entretien et réparation',
    'Avance au personnel',
    'Autre dépense',
]
MOTIFS_GRATUITE = [
    'Patient indigent',
    'Personnel du centre',
    'Programme ou campagne de santé',
    'Prise en charge sociale',
    'Autre motif',
]


def poser(apps, schema_editor):
    MotifSortie = apps.get_model('comptabilite', 'MotifSortie')
    MotifGratuite = apps.get_model('comptabilite', 'MotifGratuite')
    for libelle in MOTIFS_SORTIE:
        MotifSortie.objects.get_or_create(libelle=libelle)
    for libelle in MOTIFS_GRATUITE:
        MotifGratuite.objects.get_or_create(libelle=libelle)


def retirer(apps, schema_editor):
    apps.get_model('comptabilite', 'MotifSortie').objects.filter(
        libelle__in=MOTIFS_SORTIE, sorties__isnull=True).delete()
    apps.get_model('comptabilite', 'MotifGratuite').objects.filter(
        libelle__in=MOTIFS_GRATUITE, factures__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0002_motifgratuite_motifsortie_avoir_sortiecaisse'),
        ('facturation', '0029_caisse_seuil_sortie_facture_motif_remise'),
    ]

    operations = [
        migrations.RunPython(poser, retirer),
    ]
