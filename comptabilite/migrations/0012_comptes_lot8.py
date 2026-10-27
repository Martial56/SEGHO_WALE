from django.db import migrations

# Achats, stocks et clôture (lot 8). Les stocks se tiennent en inventaire
# intermittent : les achats vont en charge (601, 604), le stock (31x) n'est
# ajusté qu'à l'inventaire de fin d'exercice, par la variation (603x).
COMPTES = [
    ('6033', 'Variation des stocks de consommables médicaux', False),
]

CORRESPONDANCES = [
    ('fournisseur', 'Dettes envers les fournisseurs', '401'),
    ('achat:medicament', 'Achats de médicaments', '601'),
    ('achat:consommable', 'Achats de consommables médicaux', '604'),
    ('achat:equipement', "Achats d'équipement et de matériel", '241'),
    ('stock:medicament', 'Stock de médicaments (inventaire, dons en nature)', '311'),
    ('stock:consommable', 'Stock de consommables médicaux (inventaire, dons en nature)', '331'),
    ('stock:equipement', 'Matériel reçu en don', '241'),
    ('variation:medicament', 'Variation du stock de médicaments', '6031'),
    ('variation:consommable', 'Variation du stock de consommables', '6033'),
    ('resultat_excedent', "Résultat de l'exercice : excédent", '131'),
    ('resultat_deficit', "Résultat de l'exercice : déficit", '139'),
]


def poser(apps, schema_editor):
    Compte = apps.get_model('comptabilite', 'Compte')
    Correspondance = apps.get_model('comptabilite', 'Correspondance')
    for numero, intitule, a_valider in COMPTES:
        Compte.objects.get_or_create(numero=numero, defaults={'intitule': intitule, 'a_valider': a_valider})
    for cle, libelle, numero in CORRESPONDANCES:
        compte = Compte.objects.filter(numero=numero).first()
        if compte:
            Correspondance.objects.get_or_create(cle=cle, defaults={'libelle': libelle, 'compte': compte})


def retirer(apps, schema_editor):
    apps.get_model('comptabilite', 'Correspondance').objects.filter(
        cle__in=[c for c, _, _ in CORRESPONDANCES]).delete()
    apps.get_model('comptabilite', 'Compte').objects.filter(
        numero__in=[c for c, _, _ in COMPTES], lignes__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0011_lot8_achats_cloture'),
    ]

    operations = [
        migrations.RunPython(poser, retirer),
    ]
