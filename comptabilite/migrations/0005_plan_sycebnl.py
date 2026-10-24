from django.db import migrations

# Plan comptable de départ — SYCEBNL (entités à but non lucratif, OHADA).
#
# La structure des classes et les comptes courants (tiers, trésorerie, achats,
# ventes) sont ceux du plan OHADA commun au SYSCOHADA révisé et au SYCEBNL.
# Les comptes propres au non-lucratif — fonds associatifs, dons, subventions,
# organismes partenaires — sont marqués `a_valider` : leur numérotation exacte
# est à confirmer par l'expert-comptable avant la première clôture. Tout se
# corrige ensuite dans Comptabilité → Configuration → Plan comptable, sans
# toucher au code : les écritures ne connaissent que les correspondances.
#
# Les sous-comptes 706x et 411x sont des subdivisions du centre, libres dans
# le cadre OHADA.
COMPTES = [
    # Classe 1 — Ressources durables
    ('101', 'Fonds associatifs sans droit de reprise', True),
    ('102', 'Fonds associatifs avec droit de reprise', True),
    ('106', 'Réserves', False),
    ('121', 'Report à nouveau créditeur (excédents antérieurs)', False),
    ('129', 'Report à nouveau débiteur (déficits antérieurs)', False),
    ('131', "Résultat net de l'exercice : excédent", False),
    ('139', "Résultat net de l'exercice : déficit", False),
    ('141', "Subventions d'équipement", True),
    # Classe 2 — Immobilisations
    ('231', 'Bâtiments', False),
    ('241', 'Matériel et outillage (dont matériel médical)', False),
    ('244', 'Matériel et mobilier de bureau, informatique', False),
    ('245', 'Matériel de transport', False),
    # Classe 3 — Stocks
    ('311', 'Stocks de médicaments et produits pharmaceutiques', False),
    ('331', 'Stocks de consommables médicaux et réactifs', False),
    # Classe 4 — Tiers
    ('401', 'Fournisseurs', False),
    ('411', 'Usagers', False),
    ('4111', 'Patients', False),
    ('4112', 'Organismes de prise en charge (assurances, mutuelles)', False),
    ('419', 'Patients créditeurs (avances reçues)', False),
    ('421', 'Personnel, avances et acomptes', False),
    ('422', 'Personnel, rémunérations dues', False),
    ('458', 'Partenaires et bailleurs, subventions à recevoir', True),
    # Classe 5 — Trésorerie
    ('513', 'Chèques à encaisser', False),
    ('521', 'Banques', False),
    ('552', 'Monnaie électronique (Mobile Money)', False),
    ('571', 'Caisse', False),
    ('585', 'Virements de fonds', False),
    # Classe 6 — Charges
    ('601', 'Achats de médicaments et produits pharmaceutiques', False),
    ('6031', 'Variation des stocks de médicaments', False),
    ('604', 'Achats de consommables médicaux et réactifs', False),
    ('605', 'Autres achats (fournitures, eau, électricité…)', False),
    ('618', 'Frais de transport', False),
    ('624', 'Entretien, réparations et maintenance', False),
    ('661', 'Rémunérations du personnel', False),
    ('658', 'Charges diverses (dont manquants de caisse)', False),
    # Classe 7 — Ressources
    ('701', 'Ventes de médicaments (pharmacie)', False),
    ('706', 'Prestations de services', False),
    ('7061', 'Consultations', False),
    ('7062', 'Soins infirmiers', False),
    ('7063', 'Hospitalisation et mise en observation', False),
    ('7064', 'Examens de laboratoire', False),
    ('7065', 'Imagerie et explorations', False),
    ('7068', 'Autres prestations', False),
    ('709', 'Remises et gratuités accordées', False),
    ('718', "Subventions d'exploitation", True),
    ('7581', 'Dons reçus', True),
    ('7582', 'Cotisations des membres', True),
    ('758', 'Produits divers (dont excédents de caisse)', False),
]

JOURNAUX = [
    ('VTE', 'Ventes et prestations', 'ventes'),
    ('CAI', 'Caisse (paiements sans caisse désignée)', 'caisse'),
    ('MM', 'Mobile Money', 'tresorerie'),
    ('BQ', 'Banque', 'tresorerie'),
    ('ACH', 'Achats', 'achats'),
    ('OD', 'Opérations diverses', 'od'),
    ('AN', 'À-nouveaux', 'an'),
]

CORRESPONDANCES = [
    ('nature:consultation', 'Prestations — consultations', '7061'),
    ('nature:soins', 'Prestations — soins', '7062'),
    ('nature:hospitalisation', 'Prestations — hospitalisation / mise en observation', '7063'),
    ('nature:laboratoire', 'Prestations — laboratoire', '7064'),
    ('nature:imagerie', 'Prestations — imagerie', '7065'),
    ('nature:pharmacie', 'Ventes de la pharmacie', '701'),
    ('nature:autre', 'Prestations — autres ou non classées', '7068'),
    ('remise', 'Remises et gratuités accordées', '709'),
    ('patient', 'Créances sur les patients', '4111'),
    ('tiers_payant', 'Créances sur les assurances et mutuelles', '4112'),
    ('caisse', 'Caisse (défaut ; un sous-compte est créé par caisse)', '571'),
    ('mode:mobile_money', 'Encaissements Mobile Money', '552'),
    ('mode:cheque', 'Chèques reçus', '513'),
    ('mode:virement', 'Virements reçus', '521'),
    ('mode:assurance', 'Paiements pris en charge par une assurance', '4112'),
    ('mode:bon', 'Paiements par bon de prise en charge', '4112'),
    ('ecart_manquant', 'Manquants de caisse', '658'),
    ('ecart_excedent', 'Excédents de caisse', '758'),
    ('sortie_defaut', 'Sorties de caisse sans compte de motif', '605'),
]

MOTIFS_SORTIE = {
    'Achat de fournitures': '605',
    'Transport / course': '618',
    'Petit entretien et réparation': '624',
    'Avance au personnel': '421',
    'Autre dépense': '658',
}


def poser(apps, schema_editor):
    Compte = apps.get_model('comptabilite', 'Compte')
    Journal = apps.get_model('comptabilite', 'Journal')
    Correspondance = apps.get_model('comptabilite', 'Correspondance')
    MotifSortie = apps.get_model('comptabilite', 'MotifSortie')
    for numero, intitule, a_valider in COMPTES:
        Compte.objects.get_or_create(numero=numero, defaults={'intitule': intitule, 'a_valider': a_valider})
    for code, libelle, type_ in JOURNAUX:
        Journal.objects.get_or_create(code=code, defaults={'libelle': libelle, 'type': type_})
    for cle, libelle, numero in CORRESPONDANCES:
        Correspondance.objects.get_or_create(
            cle=cle, defaults={'libelle': libelle, 'compte': Compte.objects.get(numero=numero)})
    for libelle, numero in MOTIFS_SORTIE.items():
        MotifSortie.objects.filter(libelle=libelle, compte__isnull=True).update(
            compte=Compte.objects.get(numero=numero))


def retirer(apps, schema_editor):
    apps.get_model('comptabilite', 'MotifSortie').objects.update(compte=None)
    apps.get_model('comptabilite', 'Correspondance').objects.all().delete()
    apps.get_model('comptabilite', 'Journal').objects.filter(caisse__isnull=True).delete()
    apps.get_model('comptabilite', 'Compte').objects.filter(
        numero__in=[c for c, _, _ in COMPTES], lignes__isnull=True, correspondances__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0004_plan_comptable_ecritures'),
    ]

    operations = [
        migrations.RunPython(poser, retirer),
    ]
