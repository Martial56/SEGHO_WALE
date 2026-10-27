from django.db import migrations

# Trésorerie (lot 7) : comptes et correspondances, et les deux comptes de
# trésorerie de départ — la banque (521) et le Mobile Money (552), ceux
# qu'utilisent déjà les écritures des paiements par virement et Mobile Money.
COMPTES = [
    ('631', 'Frais bancaires', False),
    ('651', 'Pertes sur créances (patients, assurances)', False),
]

CORRESPONDANCES = [
    ('frais_bancaires', 'Frais bancaires et de Mobile Money', '631'),
    ('perte_creance', 'Pertes sur créances irrécouvrables', '651'),
    ('virement_interne', 'Virements de fonds internes (caisse → banque)', '585'),
]

TRESORERIE = [
    ('Banque', 'banque', '521'),
    ('Mobile Money', 'mobile_money', '552'),
]


def poser(apps, schema_editor):
    Compte = apps.get_model('comptabilite', 'Compte')
    Correspondance = apps.get_model('comptabilite', 'Correspondance')
    CompteTresorerie = apps.get_model('comptabilite', 'CompteTresorerie')
    for numero, intitule, a_valider in COMPTES:
        Compte.objects.get_or_create(numero=numero, defaults={'intitule': intitule, 'a_valider': a_valider})
    for cle, libelle, numero in CORRESPONDANCES:
        Correspondance.objects.get_or_create(
            cle=cle, defaults={'libelle': libelle, 'compte': Compte.objects.get(numero=numero)})
    for libelle, type_, numero in TRESORERIE:
        compte = Compte.objects.filter(numero=numero).first()
        if compte and not CompteTresorerie.objects.filter(compte=compte).exists():
            CompteTresorerie.objects.create(libelle=libelle, type=type_, compte=compte)


def retirer(apps, schema_editor):
    apps.get_model('comptabilite', 'CompteTresorerie').objects.filter(
        libelle__in=[l for l, _, _ in TRESORERIE], releve__isnull=True, remises__isnull=True).delete()
    apps.get_model('comptabilite', 'Correspondance').objects.filter(
        cle__in=[c for c, _, _ in CORRESPONDANCES]).delete()
    apps.get_model('comptabilite', 'Compte').objects.filter(
        numero__in=[c for c, _, _ in COMPTES], lignes__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0009_tresorerie'),
    ]

    operations = [
        migrations.RunPython(poser, retirer),
    ]
