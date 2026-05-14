from django.core.management.base import BaseCommand
from services.models import CategorieArticle, UniteMesure, ArticleService


CATEGORIES = [
    ('AE', 'Autres Examens',          'Examens bandelette et autres examens rapides'),
    ('AP', 'Accessoires Paramédicaux', 'Consommables médicaux et accessoires de soins'),
    ('CS', 'Consultations',            'Consultations médicales et spécialisées'),
    ('EC', 'Echographies',             "Examens d'imagerie par échographie"),
    ('EG', 'Electrocardiogramme',      'Examens électrocardiographiques'),
    ('EX', 'Examens Biologiques',      'Analyses biologiques et de laboratoire'),
    ('MD', 'Médicaments',              'Médicaments et produits pharmaceutiques'),
    ('MO', 'Mise en Observation',      'Hospitalisation en observation courte durée'),
    ('MT', 'Maternité',                'Prestations maternité, accouchement et suivi prénatal'),
    ('RD', 'Radiologies',              'Examens radiologiques et imagerie médicale'),
    ('SN', 'Soins',                    'Actes de soins infirmiers et médicaux divers'),
    ('VC', 'Vaccins',                  'Vaccinations et immunisations'),
]

UNITES = [
    # (nom, code, categorie)
    ('Unités',                'UNT',   'quantite'),
    ('Comprimé',              'CP',    'conditionnement'),
    ('Gélule',                'GEL',   'conditionnement'),
    ('Ampoule',               'AMP',   'conditionnement'),
    ('Flacon',                'FL',    'conditionnement'),
    ('Flaconnette',           'FLNN',  'conditionnement'),
    ('Sachet',                'SAC',   'conditionnement'),
    ('Poche',                 'PCH',   'conditionnement'),
    ('Plaquette',             'PLQ',   'conditionnement'),
    ('Boîte',                 'BTE',   'conditionnement'),
    ('Tube',                  'TB',    'conditionnement'),
    ('Cassette',              'CASS',  'conditionnement'),
    ('Compresse',             'COMP',  'conditionnement'),
    ('Bande',                 'BDE',   'conditionnement'),
    ('Seringue',              'SRG',   'conditionnement'),
    ('Paire',                 'PR',    'conditionnement'),
    ('Rouleau',               'RLX',   'conditionnement'),
    ('Bidon',                 'BDN',   'conditionnement'),
    ('Patch',                 'PATCH', 'conditionnement'),
    ('Millilitre',            'ML',    'volume'),
    ('Litre',                 'L',     'volume'),
    ('Centilitre',            'CL',    'volume'),
    ('Milligramme',           'MG',    'masse'),
    ('Gramme',                'G',     'masse'),
    ('Kilogramme',            'KG',    'masse'),
    ('Unité Internationale',  'UI',    'quantite'),
    ('Dose',                  'DOS',   'quantite'),
    ('Test',                  'TEST',  'quantite'),
    ('Lame',                  'LM',    'quantite'),
    ('Paire de gants',        'GNT',   'conditionnement'),
]

# (nom, reference_interne, prix_vente, cat_code, type_article, type_produit)
ARTICLES = [
    # ── CONSULTATIONS (CS) ────────────────────────────────────
    ('CONSULTATION ADULTE',                           'CS_CSAD',      1000,  'CS', 'service', 'service'),
    ('CONSULTATION ADULTE PERMANENCE',                'CS_CADPER',    2000,  'CS', 'service', 'service'),
    ('CONSULTATION ENFANT',                           'CS_ENFT',       500,  'CS', 'service', 'service'),
    ('CONSULTATION ENFANT PERMANENCE',                'CS_CEFTPER',   1000,  'CS', 'service', 'service'),
    ('CONSULTATION ELEVE/ETUDIANT',                   'CS_ELT',        500,  'CS', 'service', 'service'),
    ('CONSULTATION ELEVE/ETUDIANT PERMANENCE',        'CS_CELPER',    1000,  'CS', 'service', 'service'),
    ('CONSULTATION GYNECO OBSTETRIQUE',               'CS_CSGO',      3350,  'CS', 'service', 'service'),
    ('CONSULTATION GYNECOLOGIQUE SIMPLE',             'CS_CSG',       4050,  'CS', 'service', 'service'),
    ('CONSULTATION CARDIOLOGIQUE SPECIALE',           'CS_CSCARDIO',  5000,  'CS', 'service', 'service'),
    ('CONSULTATION SPECIALISTE PRIVE',                'CS_CSSP',      5000,  'CS', 'service', 'service'),
    ('CONSULTATION DERMATOLOGIE',                     'CS-DERMATO',   5000,  'CS', 'service', 'service'),
    ('CONSULTATION DIABETOLOGIE',                     'CS-DIABETO',   5000,  'CS', 'service', 'service'),
    ('CONSULTATION PRENATALE',                        'CS-CPN',        500,  'CS', 'service', 'service'),
    ('REMPLISSAGE BON MUTUELLE',                      'CS_CMUTUEL',    500,  'CS', 'service', 'service'),

    # ── ECHOGRAPHIES (EC) ─────────────────────────────────────
    ('ECHOGRAPHIE',                                   'EC_ECHO',      7000,  'EC', 'service', 'examen'),
    ('ECHOGRAPHIE DOPPLER',                           'EC_DOPLER',   40000,  'EC', 'service', 'examen'),
    ('ECHOGRAPHIE SPECIFIQUE',                        'EC_ECHOS',    12000,  'EC', 'service', 'examen'),
    ('ECHO ABDO-PELVIEN EXTERNE',                     'EC_ECHOA',    15000,  'EC', 'service', 'examen'),
    ('ECHO ABDO-PELVIEN INTERNE',                     'EC_ECHOAB',   10000,  'EC', 'service', 'examen'),
    ('ECHOGRAPHIE EXTERNE',                           'EC_ECHO2',    10000,  'EC', 'service', 'examen'),

    # ── EXAMENS BIOLOGIQUES (EX) ──────────────────────────────
    ('ACIDE URIQUE',                                  'EX_ACIDUR',    3500,  'EX', 'service', 'examen'),
    ('ASLO',                                          'EX_ASLO',      4000,  'EX', 'service', 'examen'),
    ('BILIRUBINE DIRECTE',                            'EX_BRILDI',    5000,  'EX', 'service', 'examen'),
    ('BILIRUBINE TOTALE',                             'EX_BRILTO',    5000,  'EX', 'service', 'examen'),
    ('CHOLESTEROL HDL',                               'EX_CHLST1',    4000,  'EX', 'service', 'examen'),
    ('CHOLESTEROL TOTAL',                             'EX_CHLST2',    2000,  'EX', 'service', 'examen'),
    ('CHOLESTEROL LDL',                               'EX_CHOLESTLDL',3000,  'EX', 'service', 'examen'),
    ('EXAMEN CHOLESTEROL',                            'EX_CHOLST',    2500,  'EX', 'service', 'examen'),
    ('PROTEINE REACTIVE (CRP)',                       'EX_CRP',       4500,  'EX', 'service', 'examen'),
    ('ECBU',                                          'EX_ECBU',      4000,  'EX', 'service', 'examen'),
    ('ELECTROPHORESE D\'HEMOGLOBINE',                 'EX_ELECT',     5000,  'EX', 'service', 'examen'),
    ('EXAMEN BW (SYPHILIS)',                          'EX_EXBW',      1500,  'EX', 'service', 'examen'),
    ('EXAMEN CALCEMIE',                               'EX_EXCALC',    2000,  'EX', 'service', 'examen'),
    ('EXAMEN CREATININE',                             'EX_EXCREA',    1500,  'EX', 'service', 'examen'),
    ('EXAMEN FIEVRE TYPHOIDE',                        'EX_EXFTHY',    4000,  'EX', 'service', 'examen'),
    ('EXAMEN GLYCEMIE',                               'EX_EXGLYC',    1500,  'EX', 'service', 'examen'),
    ('EXAMEN GROUPE RHESUS',                          'EX_EXGRHE',    1000,  'EX', 'service', 'examen'),
    ('EXAMEN MAGNESIUM',                              'EX_EXMGN',     2000,  'EX', 'service', 'examen'),
    ('EXAMEN RUBEOLE',                                'EX_EXRUBE',    4000,  'EX', 'service', 'examen'),
    ('EXAMEN TOXOPLASMOSE',                           'EX_EXTOXO',    4000,  'EX', 'service', 'examen'),
    ('EXAMEN TRIGLYCERIDE',                           'EX_EXTRIG',    3000,  'EX', 'service', 'examen'),
    ('EXAMEN UREE',                                   'EX_EXUREE',    1500,  'EX', 'service', 'examen'),
    ('EXAMEN ACIDE URIQUE',                           'EX_EXURIQ',    3500,  'EX', 'service', 'examen'),
    ('GOUTTE EPAISSE (PALU)',                         'EX_GTEPSS',    1500,  'EX', 'service', 'examen'),
    ('TEST RAPIDE DE PALU',                           'EX_GTTERA',    1000,  'EX', 'service', 'examen'),
    ('ANTICORPS ANTI HBC',                            'EX_HBCAB',     4000,  'EX', 'service', 'examen'),
    ('ANTICORPS ANTI HBE',                            'EX_HBEAB',     4000,  'EX', 'service', 'examen'),
    ('ANTICORPS ANTI HBS',                            'EX_HBSAB',     4000,  'EX', 'service', 'examen'),
    ('ANTIGENE HBE',                                  'EX_HBEAG',     4000,  'EX', 'service', 'examen'),
    ('ANTIGENE HBS',                                  'EX_HBSAG',     4000,  'EX', 'service', 'examen'),
    ('HEMOGLOBINE GLYQUEE (HbA1c)',                   'EX_HEMOGLYQUEE',7000, 'EX', 'service', 'examen'),
    ('ANTICORPS HVC',                                 'EX_HVC',       4000,  'EX', 'service', 'examen'),
    ('IONOGRAMME',                                    'EX_IONO',      7000,  'EX', 'service', 'examen'),
    ('MICROALBUMINEMIE',                              'EX_MICROALB',  7000,  'EX', 'service', 'examen'),
    ('NUMERATION FORMULE SANGUINE (NFS)',             'EX_NFS',       4000,  'EX', 'service', 'examen'),
    ('POTASSIUM',                                     'EX_POTA',      3000,  'EX', 'service', 'examen'),
    ('PROTEINE TOTALE',                               'EX_PROTT',     3000,  'EX', 'service', 'examen'),
    ('TAUX D\'HEMOGLOBINE',                           'EX_TAUXHEMO',  2000,  'EX', 'service', 'examen'),
    ('TEMPS DE CEPHALINE-KAOLIN (TCK)',               'EX_TCK',       4500,  'EX', 'service', 'examen'),
    ('TAUX DE PROTHROMBINE (TP)',                     'EX_TP',        4500,  'EX', 'service', 'examen'),
    ('TPHA (SYPHILIS)',                               'EX_TPHA',      4000,  'EX', 'service', 'examen'),
    ('TRANSAMINASE (TGO/TGP)',                        'EX_TRANSA',    4000,  'EX', 'service', 'examen'),
    ('VITESSE DE SEDIMENTATION (VS)',                 'EX_VS',        1000,  'EX', 'service', 'examen'),

    # ── AUTRES EXAMENS (AE) ───────────────────────────────────
    ('ACETONURIE',                                    'AE_ACE',       1000,  'AE', 'service', 'examen'),
    ('PROTEINURIE',                                   'AE_ALB',        500,  'AE', 'service', 'examen'),
    ('EXAMENS GLYCOSURIE',                            'AE_GLYCO',     1000,  'AE', 'service', 'examen'),
    ('GLYCEMIE DIABETIQUE',                           'AE_GLYDI',     1000,  'AE', 'service', 'examen'),
    ('EXAMENS HEMATURIE',                             'AE_HEM',       1000,  'AE', 'service', 'examen'),
    ('HYSTERIOLOGIE',                                 'AE_HYS',      18000,  'AE', 'service', 'examen'),

    # ── ELECTROCARDIOGRAMME (EG) ──────────────────────────────
    ('ELECTROCARDIOGRAMME',                           'EG_ECG',       7000,  'EG', 'service', 'examen'),

    # ── RADIOLOGIES (RD) ──────────────────────────────────────
    ('RADIO CAVUM',                                   'RD_CAVUM',     5500,  'RD', 'service', 'examen'),
    ('RADIO CAVUM (variante)',                        'RD_RCAVUM',    5500,  'RD', 'service', 'examen'),
    ('ASP FACE',                                      'RD_ASP',       5000,  'RD', 'service', 'examen'),
    ('AVANT BRAS FACE/PROFIL',                        'RD_AVBFP',     5000,  'RD', 'service', 'examen'),
    ('BILIRUBINE DIRECTE (RD)',                       'RD_BILDI',     5000,  'RD', 'service', 'examen'),
    ('BILIRUBINE TOTALE (RD)',                        'RD_BILTO',     5000,  'RD', 'service', 'examen'),
    ('BLONDEAU',                                      'RD_BLOND',     5500,  'RD', 'service', 'examen'),
    ('BRAS FACE/PROFIL',                              'RD_BRAFP',     5000,  'RD', 'service', 'examen'),
    ('CLAVICULE',                                     'RD_CLAVIC',    6500,  'RD', 'service', 'examen'),
    ('COUDE FACE/PROFIL',                             'RD_COUFP',     5000,  'RD', 'service', 'examen'),
    ('CRANE FACE/PROFIL',                             'RD_CRAFP',     7000,  'RD', 'service', 'examen'),
    ('EPAULE FACE/PROFIL',                            'RD_EPAFP',     6500,  'RD', 'service', 'examen'),
    ('FACE BASSE/HAUTE',                              'RD_FABH',      5500,  'RD', 'service', 'examen'),
    ('HIRTZ',                                         'RD_EHIRTZ',    5500,  'RD', 'service', 'examen'),
    ('HSG',                                           'RD_HSG',      18000,  'RD', 'service', 'examen'),
    ('MACILLAIRE',                                    'RD_MAXIL',     5500,  'RD', 'service', 'examen'),
    ('MAIN FACE/PROFIL',                              'RD_MAIFP',     5000,  'RD', 'service', 'examen'),
    ('OMOPLATE',                                      'RD_OMOPLA',    6500,  'RD', 'service', 'examen'),
    ('POIGNET FACE/PROFIL',                           'RD_RADPGF',    5000,  'RD', 'service', 'examen'),
    ('RADIO BASSIN FACE',                             'RD_BASS',      5000,  'RD', 'service', 'examen'),
    ('RADIO CHEVILLE FACE/PROFIL',                    'RD_CHE',       5000,  'RD', 'service', 'examen'),
    ('RADIO CUISSE',                                  'RD_CUIS',      6500,  'RD', 'service', 'examen'),
    ('RADIO DU COU',                                  'RD_COU',       9000,  'RD', 'service', 'examen'),
    ('RADIO DU DOIGT',                                'RD_DOIGT',     5000,  'RD', 'service', 'examen'),
    ('RADIO DU NEZ',                                  'RD_NEZ',       5500,  'RD', 'service', 'examen'),
    ('RADIO DU THORAX FACE/PROFIL',                   'RD_THORAXFP',  10000, 'RD', 'service', 'examen'),
    ('RADIO FACE',                                    'RD_FACE',      5000,  'RD', 'service', 'examen'),
    ('RADIO FEMUR FACE/PROFIL',                       'RD_FEM',       6500,  'RD', 'service', 'examen'),
    ('RADIO GENOU FACE/PROFIL',                       'RD_GEN',       5000,  'RD', 'service', 'examen'),
    ('RADIO HANCHE',                                  'RD_HCH',       5000,  'RD', 'service', 'examen'),
    ('RADIO JAMBE FACE/PROFIL',                       'RD_JMB',       5000,  'RD', 'service', 'examen'),
    ('RADIO OPN',                                     'RD_OPN',       5500,  'RD', 'service', 'examen'),
    ('RADIO PIED FACE/PROFIL',                        'RD_PIE',       5000,  'RD', 'service', 'examen'),
    ('RADIO POIGNET FACE/PROFIL',                     'RD_PGFP',      5000,  'RD', 'service', 'examen'),
    ('RADIO POUMON FACE',                             'RD_PMF',       5000,  'RD', 'service', 'examen'),
    ('RADIO POUMON FACE/PROFIL',                      'RD_PMP',       9500,  'RD', 'service', 'examen'),
    ('RACHIS CERVICAL FACE/PROFIL',                   'RD_RACFP',     9000,  'RD', 'service', 'examen'),
    ('RACHIS CERVICAL 3/4',                           'RD_RAC34',    15000,  'RD', 'service', 'examen'),
    ('RACHIS DORSAL FACE/PROFIL',                     'RD_RADFP',     9000,  'RD', 'service', 'examen'),
    ('RACHIS LOMBAIRE FACE/PROFIL',                   'RD_RALFP',     9000,  'RD', 'service', 'examen'),
    ('RACHIS LOMBAIRE 3/4',                           'RD_RAL34',    15000,  'RD', 'service', 'examen'),
    ('TELECOEUR',                                     'RD_TELECO',    5000,  'RD', 'service', 'examen'),
    ('THORAX OSSEUX FACE',                            'RD_TOROS',     5000,  'RD', 'service', 'examen'),

    # ── SOINS (SN) ────────────────────────────────────────────
    ('AMBULANCE EVACUATION CHR-MOSCATI',              'SN_AMBY',      5000,  'SN', 'service', 'service'),
    ('AMBULANCE TRANSPORT ABIDJAN',                   'SN_AMBA',     90000,  'SN', 'service', 'service'),
    ('AMBULANCE TRANSPORT BOUAKE',                    'SN_AMBB',     70000,  'SN', 'service', 'service'),
    ('AMBULANCE TRANSPORT TOUMBOKRO',                 'SN_AMBT',     25000,  'SN', 'service', 'service'),
    ('AMBULANCE TRANSPORT VILLAGE',                   'SN_AMBV',     10000,  'SN', 'service', 'service'),
    ('CERTIFICAT MEDICAL',                            'SN_CERMED',    5000,  'SN', 'service', 'service'),
    ('CERTIFICAT DE PRISE DE TENSION ARTERIELLE',     'SN_CERTTA',    5000,  'SN', 'service', 'service'),
    ('CIRCONCISION',                                  'SN_CIRCO',     5000,  'SN', 'service', 'service'),
    ('COUPURE DE FREIN DE LANGUE',                    'SN_FRLANG',    1000,  'SN', 'service', 'service'),
    ('DRAINAGE',                                      'SN_DRAIN',     7000,  'SN', 'service', 'service'),
    ('FIL',                                           'SN_FIL',       2000,  'SN', 'service', 'service'),
    ('FIL + SUTURE',                                  'SN_SUTURE',    5000,  'SN', 'service', 'service'),
    ('INJECTION EXTERNE',                             'SN_INJEXT',     200,  'SN', 'service', 'service'),
    ('INJECTION INTERNE',                             'SN_INJINT',       0,  'SN', 'service', 'service'),
    ('LAVAGE D\'OREILLE',                             'SN_LAVORE',    1000,  'SN', 'service', 'service'),
    ('LAVAGE NASAL',                                  'SN-LAVNA',        0,  'SN', 'service', 'service'),
    ('MISE EN OBSERVATION (VENTE)',                   'SN_MEOVEN',    2000,  'SN', 'service', 'service'),
    ('NEBULISATION',                                  'SN_NEB',       1500,  'SN', 'service', 'service'),
    ('ONGLE INCARNE',                                 'SN_ONGINC',    2500,  'SN', 'service', 'service'),
    ('OXYGENATION (DIX MINUTES)',                     'SN_OXYGEN',    1000,  'SN', 'service', 'service'),
    ('PANSEMENT GRANDE PLAIE',                        'SN_PSTGPL',    2000,  'SN', 'service', 'service'),
    ('PANSEMENT MOYENNE PLAIE',                       'SN_PSTMPL',    1000,  'SN', 'service', 'service'),
    ('PANSEMENT PETITE PLAIE',                        'SN_PSTPPL',     500,  'SN', 'service', 'service'),
    ('PONCTION',                                      'SN_PONCT',     1000,  'SN', 'service', 'service'),
    ('PRISE DE TENSION ARTERIELLE',                   'SN_PTA',        200,  'SN', 'service', 'service'),
    ('SUTURE PLAIE TRAUMATIQUE',                      'SN-PLAITRAU',  5000,  'SN', 'service', 'service'),

    # ── MISE EN OBSERVATION (MO) ──────────────────────────────
    ('MISE EN OBSERVATION',                           'MO_MEO',       2000,  'MO', 'service', 'service'),

    # ── MATERNITE (MT) ────────────────────────────────────────
    ('ACCOUCHEMENT',                                  'MTACC',       15000,  'MT', 'service', 'service'),
    ('ACCOUCHEMENT A DOMICILE',                       'MTACCD',       9150,  'MT', 'service', 'service'),
    ('TEST URINE (MATERNITE)',                        'MT_ALB',        500,  'MT', 'service', 'examen'),

    # ── VACCINS (VC) ──────────────────────────────────────────
    ('VACCIN ANTITETANIQUE',                          'VC_VAT',        500,  'VC', 'service', 'service'),
    ('VACCIN BCG',                                    'VC_VBCG',       500,  'VC', 'service', 'service'),
    ('VACCIN DTCOQ POLIO',                            'VC_DTCOQ',      500,  'VC', 'service', 'service'),
    ('VACCIN FIEVRE JAUNE',                           'VC_FJAUN',      500,  'VC', 'service', 'service'),
    ('VACCIN ROUGEOLE',                               'VC_ROUGE',      500,  'VC', 'service', 'service'),
]


class Command(BaseCommand):
    help = 'Seed des catégories, unités de mesure et articles/services'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Supprimer les articles existants avant le seed')

    def handle(self, *args, **options):
        if options['clear']:
            ArticleService.objects.all().delete()
            self.stdout.write(self.style.WARNING('Articles supprimés.'))

        # 1. Catégories
        self.stdout.write('→ Catégories...')
        cat_map = {}
        for code, nom, desc in CATEGORIES:
            obj, created = CategorieArticle.objects.get_or_create(
                code=code, defaults={'nom': nom, 'description': desc}
            )
            if not created:
                obj.nom = nom
                obj.description = desc
                obj.save()
            cat_map[code] = obj
        self.stdout.write(self.style.SUCCESS(f'  {len(CATEGORIES)} catégories OK'))

        # 2. Unités de mesure
        self.stdout.write('→ Unités de mesure...')
        for nom, code, categorie in UNITES:
            UniteMesure.objects.get_or_create(
                code=code, defaults={'nom': nom, 'categorie': categorie}
            )
        self.stdout.write(self.style.SUCCESS(f'  {len(UNITES)} unités OK'))

        # 3. Articles / Services
        self.stdout.write('→ Articles / Services...')
        created_count = 0
        updated_count = 0
        for nom, ref, prix, cat_code, type_art, type_prod in ARTICLES:
            cat = cat_map.get(cat_code)
            obj, created = ArticleService.objects.get_or_create(
                reference_interne=ref,
                defaults={
                    'nom': nom,
                    'prix_vente': prix,
                    'categorie': cat,
                    'type_article': type_art,
                    'type_produit_hospitalier': type_prod,
                    'peut_etre_vendu': True,
                    'peut_etre_achete': False,
                    'actif': True,
                }
            )
            if created:
                created_count += 1
            else:
                # mise à jour si le nom ou le prix a changé
                changed = False
                if obj.nom != nom:
                    obj.nom = nom
                    changed = True
                if obj.prix_vente != prix:
                    obj.prix_vente = prix
                    changed = True
                if obj.categorie != cat:
                    obj.categorie = cat
                    changed = True
                if changed:
                    obj.save()
                    updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'  {created_count} articles créés, {updated_count} mis à jour'
        ))
        self.stdout.write(self.style.SUCCESS('✓ Seed terminé avec succès.'))
