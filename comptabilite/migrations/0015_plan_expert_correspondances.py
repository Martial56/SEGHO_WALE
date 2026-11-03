from django.db import migrations

# Plan de l'expert-comptable (export Sage 100, docs/PLAN COMPTABLE.xlsx) :
# les écritures automatiques passent sur ses comptes à 8 chiffres. Les comptes
# cibles sont créés ici s'ils manquent (l'import du fichier complet se fait à
# l'écran) ; une correspondance n'est rebranchée que si elle pointe encore sur
# le compte semé d'origine — un choix fait à l'écran est respecté.

# numéro → (intitulé du plan de l'expert, nature, à confirmer)
COMPTES = {
    '12810000': ('RESULT NET EN INST AFFECT-EXCEDENT', 'resultat_bilan', False),
    '12890000': ('RESULT EN INST AFFECT-DEFICIT', 'resultat_bilan', False),
    '24150000': ('MATERIELS MEDICALS', 'immobilisation', False),
    '32100000': ('STOCKS DE MARCHANDISES', 'stock', False),
    '33100001': ('CONSOMMABLES SALLE DE SOINS', 'stock', False),
    '40110000': ('FOURN-ACH DE BIENS ET SERVICES', 'fournisseur', False),
    '41250000': ('CLIENTS-USAGES,VTE DE MARCH,SERV ET', 'client', False),
    '41250001': ('CLIENTS ASSURANCES', 'client', False),
    '42110000': ('PERSONNEL, AVANCES', 'salarie', False),
    # Absent du plan de l'expert, qui n'a que le compte de totalisation 51300000.
    '51310000': ('CHEQUES A ENCAISSER', '', True),
    '52110002': ('SIB COMPTE PRINCIPAL', '', True),
    '55200000': ('MONNAIE ELECT-TELEPHONE PORTABLE', '', False),
    '55800001': ('ORANGE MONEY', '', False),
    '55800002': ('WAVE', '', False),
    # Absent du plan de l'expert, rangé à la suite d'Orange Money et Wave.
    '55800003': ('MTN MOMO', '', True),
    '57100001': ('CAISSE ACCUEIL', '', False),
    '57100002': ('CAISSE PHARMACIE', '', False),
    '57100003': ('CAISSE TOUMBOKRO', '', False),
    '57100004': ('CAISSE PRINCIPALE', '', False),
    '57100005': ('PETITE CAISSE', '', False),
    '58500000': ('VIREMENT DE FONDS', '', False),
    '60210001': ('ACHAT PDTS PHARMACEUTIQUES', 'charge', False),
    '60320000': ('VAR STK DE MARCHANDISES', 'charge', False),
    '60330000': ('VAR STK DE MAT PR ET FOURN LIEES', 'charge', False),
    '60410000': ('ACH STKE MATIERES CONSOMMABLES', 'charge', False),
    '60580001': ('Autres achats', 'charge', False),
    '61830002': ('Autres frais de transports', 'charge', False),
    '62480000': ('AUTRES ENTRETIENS ET REPARATIONS', 'charge', False),
    '63180000': ('AUTRES FRAIS BANCAIRES', 'charge', False),
    '65110000': ('CLIENTS-USAGERS', 'charge', False),
    '65150010': ('Pertes diverses/versements caisses', 'charge', False),
    '65880000': ('Autres charges diverses', 'charge', False),
    '70410000': ('DONS', 'produit', False),
    '70510001': ('VENTE DE MEDICAMENTS', 'produit', False),
    '70520100': ('CONSULTATIONS ADULTES', 'produit', False),
    '70522001': ('EXAMENS DE LABORATOIRE', 'produit', False),
    '70522002': ('RADIOLOGIES', 'produit', False),
    '70523001': ('MISE EN OBSERVATION', 'produit', False),
    '70523002': ('SOINS INFIRMIER', 'produit', False),
    '70524002': ('AUTRES PRESTATIONS', 'produit', False),
    '71300200': ("SUBV D'EXPL VERSEE/ ORGAN INTERNAT", 'produit', False),
    '75880000': ('AUTRES PRODUITS DIVERS', 'produit', False),
}

# clé de correspondance → (compte semé, compte de l'expert). Restent sur le
# plan semé, faute d'équivalent chez l'expert : remise (709), fonds dédiés
# (195, 689, 789).
CORRESPONDANCES = {
    'achat:consommable': ('604', '60410000'),
    'achat:equipement': ('241', '24150000'),
    'achat:medicament': ('601', '60210001'),
    'caisse': ('571', '57100004'),
    'don': ('7581', '70410000'),
    'don_nature_actif': ('311', '32100000'),
    'ecart_excedent': ('758', '75880000'),
    'ecart_manquant': ('658', '65150010'),
    'fournisseur': ('401', '40110000'),
    'frais_bancaires': ('631', '63180000'),
    'mode:assurance': ('4112', '41250001'),
    'mode:bon': ('4112', '41250001'),
    'mode:cheque': ('513', '51310000'),
    'mode:mobile_money': ('552', '55200000'),
    'mode:virement': ('521', '52110002'),
    'nature:autre': ('7068', '70524002'),
    'nature:consultation': ('7061', '70520100'),
    'nature:hospitalisation': ('7063', '70523001'),
    'nature:imagerie': ('7065', '70522002'),
    'nature:laboratoire': ('7064', '70522001'),
    'nature:pharmacie': ('701', '70510001'),
    'nature:soins': ('7062', '70523002'),
    'patient': ('4111', '41250000'),
    'perte_creance': ('651', '65110000'),
    'resultat_deficit': ('139', '12890000'),
    'resultat_excedent': ('131', '12810000'),
    'sortie_defaut': ('605', '60580001'),
    'stock:consommable': ('331', '33100001'),
    'stock:equipement': ('241', '24150000'),
    'stock:medicament': ('311', '32100000'),
    'subvention_defaut': ('718', '71300200'),
    'tiers_payant': ('4112', '41250001'),
    'variation:consommable': ('6033', '60330000'),
    'variation:medicament': ('6031', '60320000'),
    'virement_interne': ('585', '58500000'),
}

# Sous-compte de chaque caisse, reconnue à son nom.
CAISSES = [('PHARMA', '57100002'), ('ACCU', '57100001'), ('TOUMBOKRO', '57100003'),
           ('PRINCIPAL', '57100004'), ('PETITE', '57100005')]

TRESORERIE = {'521': '52110002', '552': '55200000', '5521': '55800002', '5522': '55800001', '5523': '55800003'}

MOTIFS = {'605': '60580001', '658': '65880000', '421': '42110000', '624': '62480000', '618': '61830002'}


def _encore_designe(apps, compte):
    for modele, champ in (('Correspondance', 'compte'), ('CompteTresorerie', 'compte'), ('MotifSortie', 'compte'),
                          ('Convention', 'compte_ressource'), ('LigneBudgetaire', 'compte')):
        if apps.get_model('comptabilite', modele)._base_manager.filter(**{champ: compte}).exists():
            return True
    return False


def poser(apps, schema_editor):
    Compte = apps.get_model('comptabilite', 'Compte')
    Correspondance = apps.get_model('comptabilite', 'Correspondance')
    CompteTresorerie = apps.get_model('comptabilite', 'CompteTresorerie')
    MotifSortie = apps.get_model('comptabilite', 'MotifSortie')
    Caisse = apps.get_model('facturation', 'Caisse')

    comptes = {}
    for numero, (intitule, nature, a_valider) in COMPTES.items():
        comptes[numero], _ = Compte.objects.get_or_create(
            numero=numero, defaults={'intitule': intitule, 'nature': nature, 'a_valider': a_valider})

    anciens = set()
    for cle, (ancien, nouveau) in CORRESPONDANCES.items():
        if Correspondance.objects.filter(cle=cle, compte__numero=ancien).update(compte=comptes[nouveau]):
            anciens.add(ancien)
    for corr in Correspondance.objects.filter(cle__startswith='caisse:', compte__numero__regex=r'^571\d?$'):
        caisse = Caisse.objects.filter(code=corr.cle.split(':', 1)[1]).first()
        nom = (caisse.nom if caisse else '').upper()
        numero = next((n for mot, n in CAISSES if mot in nom), None)
        if numero and not Correspondance.objects.filter(cle__startswith='caisse:', compte=comptes[numero]).exists():
            anciens.add(corr.compte.numero)
            corr.compte = comptes[numero]
            corr.save(update_fields=['compte'])
    for ancien, nouveau in TRESORERIE.items():
        if not CompteTresorerie.objects.filter(compte=comptes[nouveau]).exists() and \
                CompteTresorerie.objects.filter(compte__numero=ancien).update(compte=comptes[nouveau]):
            anciens.add(ancien)
    for ancien, nouveau in MOTIFS.items():
        if MotifSortie.objects.filter(compte__numero=ancien).update(compte=comptes[nouveau]):
            anciens.add(ancien)

    # Les comptes semés remplacés ne se proposent plus à la saisie ; leurs
    # écritures passées restent dans les états.
    for compte in Compte.objects.filter(numero__in=anciens, actif=True):
        if not _encore_designe(apps, compte):
            compte.actif = False
            compte.save(update_fields=['actif'])


def retirer(apps, schema_editor):
    Compte = apps.get_model('comptabilite', 'Compte')
    Correspondance = apps.get_model('comptabilite', 'Correspondance')
    CompteTresorerie = apps.get_model('comptabilite', 'CompteTresorerie')
    MotifSortie = apps.get_model('comptabilite', 'MotifSortie')
    for cle, (ancien, nouveau) in CORRESPONDANCES.items():
        compte = Compte.objects.filter(numero=ancien).first()
        if compte:
            Correspondance.objects.filter(cle=cle, compte__numero=nouveau).update(compte=compte)
    for ancien, nouveau in list(TRESORERIE.items()):
        compte = Compte.objects.filter(numero=ancien).first()
        if compte and not CompteTresorerie.objects.filter(compte=compte).exists():
            CompteTresorerie.objects.filter(compte__numero=nouveau).update(compte=compte)
    for ancien, nouveau in MOTIFS.items():
        compte = Compte.objects.filter(numero=ancien).first()
        if compte:
            MotifSortie.objects.filter(compte__numero=nouveau).update(compte=compte)
    anciens = {a for a, _ in CORRESPONDANCES.values()} | set(TRESORERIE) | set(MOTIFS)
    Compte.objects.filter(numero__in=anciens).update(actif=True)


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0014_plan_import'),
        ('facturation', '0032_paiement_operateur'),
    ]

    operations = [
        migrations.RunPython(poser, retirer),
    ]
