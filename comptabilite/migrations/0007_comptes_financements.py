from django.db import migrations

# Comptes et correspondances des financements (lot 5).
#
# Les fonds dédiés suivent la logique habituelle des entités à but non
# lucratif : en fin d'exercice, la part d'une ressource affectée non encore
# utilisée est sortie du résultat (charge « engagements à réaliser ») et
# portée en fonds dédiés ; elle revient l'année où elle est consommée
# (ressource « report des ressources non utilisées »). Les trois numéros
# ci-dessous sont marqués `a_valider` : la numérotation SYCEBNL exacte est à
# confirmer par l'expert-comptable, puis à corriger à l'écran si besoin.
COMPTES = [
    ('195', 'Fonds dédiés sur ressources affectées', True),
    ('689', 'Engagements à réaliser sur ressources affectées', True),
    ('789', 'Report des ressources affectées non utilisées des exercices antérieurs', True),
]

CORRESPONDANCES = [
    ('subvention_defaut', "Subventions d'exploitation (compte proposé pour une convention)", '718'),
    ('don', 'Dons reçus', '7581'),
    ('don_nature_actif', 'Dons en nature — actif reçu par défaut (médicaments)', '311'),
    ('fonds_dedies', 'Fonds dédiés', '195'),
    ('engagement_fonds_dedies', 'Engagements à réaliser sur ressources affectées', '689'),
    ('report_fonds_dedies', 'Report des ressources affectées non utilisées', '789'),
]


def poser(apps, schema_editor):
    Compte = apps.get_model('comptabilite', 'Compte')
    Correspondance = apps.get_model('comptabilite', 'Correspondance')
    for numero, intitule, a_valider in COMPTES:
        Compte.objects.get_or_create(numero=numero, defaults={'intitule': intitule, 'a_valider': a_valider})
    for cle, libelle, numero in CORRESPONDANCES:
        Correspondance.objects.get_or_create(
            cle=cle, defaults={'libelle': libelle, 'compte': Compte.objects.get(numero=numero)})


def retirer(apps, schema_editor):
    apps.get_model('comptabilite', 'Correspondance').objects.filter(
        cle__in=[c for c, _, _ in CORRESPONDANCES]).delete()
    apps.get_model('comptabilite', 'Compte').objects.filter(
        numero__in=[c for c, _, _ in COMPTES], lignes__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0006_financements'),
    ]

    operations = [
        migrations.RunPython(poser, retirer),
    ]
