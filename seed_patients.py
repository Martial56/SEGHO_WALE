import os
import django
import random
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medisoft.settings')
django.setup()

from patients.models import Patient, Assurance

ass1, _ = Assurance.objects.get_or_create(code='CNAM-CI',     defaults={'nom': 'CNAM Côte d\'Ivoire',   'taux_prise_en_charge': 70})
ass2, _ = Assurance.objects.get_or_create(code='MUGEF-CI',    defaults={'nom': 'MUGEF-CI',               'taux_prise_en_charge': 80})
ass3, _ = Assurance.objects.get_or_create(code='SANTE-PLUS',  defaults={'nom': 'Santé Plus',             'taux_prise_en_charge': 60})
assurances = [ass1, ass2, ass3]

hommes = [
    ('KONÉ',      'Mamadou Issouf',      date(1985,  3, 14), 'Bouaké',         '0705182341', 'M', 'Chauffeur',     'Yamoussoukro', 'AB+'),
    ('TRAORÉ',    'Seydou Adama',        date(1978, 11,  2), 'Yamoussoukro',   '0102934752', 'M', 'Enseignant',    'Yamoussoukro', 'O+'),
    ('COULIBALY', 'Ibrahim Kalil',       date(1993,  6, 27), 'Abidjan',        '0778456123', 'M', 'Informaticien', 'Abidjan',      'A+'),
    ('DIABATÉ',   'Oumar Fousseyni',     date(1970,  8,  5), 'Katiola',        '0547891234', 'M', 'Commerçant',    'Yamoussoukro', 'B-'),
    ('BAMBA',     'Adama Souleymane',    date(2001,  1, 19), 'Korhogo',        '0167234890', 'M', 'Étudiant',      'Korhogo',      'O-'),
    ('OUATTARA',  'Bakary Drissa',       date(1965,  9, 30), 'Ferkessédougou', '0748923410', 'M', 'Agriculteur',   'Yamoussoukro', 'A-'),
    ('DEMBÉLÉ',   'Lassina Boubacar',    date(1988,  4, 12), 'Man',            '0156784320', 'M', 'Mécanicien',    'Man',          'B+'),
    ('SANOGO',    'Bénié Honoré',        date(1975, 12, 22), 'Daloa',          '0738451267', 'M', 'Infirmier',     'Daloa',        'AB-'),
    ('FOFANA',    'Moussa Karidjatou',   date(1999,  7,  8), 'Odienné',        '0617293841', 'M', 'Apprenti',      'Yamoussoukro', 'O+'),
    ('CISSÉ',     'Cheick Tidiane',      date(1982,  2, 25), 'San-Pédro',      '0785634921', 'M', 'Pêcheur',       'San-Pédro',    'A+'),
]

femmes = [
    ('KONAN',     'Adjoua Marie-Claire', date(1990,  5,  3), 'Yamoussoukro',   '0704512378', 'F', 'Secrétaire',    'Yamoussoukro', 'O+'),
    ('YAO',       'Akissi Rosine',       date(1984,  8, 17), 'Abengourou',     '0559871234', 'F', 'Commerçante',   'Abengourou',   'A+'),
    ('NGUESSAN',  'Aya Inès',            date(1997,  3, 29), 'Grand-Bassam',   '0778123456', 'F', 'Étudiante',     'Yamoussoukro', 'B+'),
    ('KOUASSI',   'Amenan Fatou',        date(1972, 10, 11), 'Tiassalé',       '0107659823', 'F', 'Ménagère',      'Tiassalé',     'AB+'),
    ('BROU',      'Affoué Stéphanie',    date(2003,  1,  6), 'Abidjan',        '0678345219', 'F', 'Lycéenne',      'Abidjan',      'O-'),
    ('ASSI',      'Kouassi Hortense',    date(1968,  6, 20), 'Agboville',      '0547832190', 'F', 'Agricultrice',  'Agboville',    'A-'),
    ('KOFFI',     'Adjoua Céline',       date(1995,  9, 14), 'Bondoukou',      '0769234510', 'F', 'Infirmière',    'Bondoukou',    'B-'),
    ('AHOU',      'Christelle Nda',      date(1987,  4,  2), 'Dimbokro',       '0587341260', 'F', 'Enseignante',   'Dimbokro',     'AB-'),
    ('TOURÉ',     'Mariam Fatimata',     date(2000, 11, 28), 'Séguéla',        '0758921340', 'F', 'Étudiante',     'Séguéla',      'O+'),
    ('DIOMANDÉ',  'Aissata Karidja',     date(1979,  7, 16), 'Touba',          '0625473918', 'F', 'Sage-femme',    'Touba',        'A+'),
]

allergies_list = [
    'Pénicilline', 'Aspirine', 'Sulfamides', 'AINS', '',
    'Latex', 'Iode', 'Amoxicilline', '', 'Codéine',
]
antecedents_list = [
    'Hypertension artérielle traitée',
    'Diabète type 2 sous metformine',
    'Asthme bronchique intermittent',
    'Paludisme chronique (3 épisodes)',
    'Drépanocytose (trait AS)',
    'Tuberculose pulmonaire traitée (2020)',
    'Appendicectomie (2015)',
    '',
    'Cardiopathie rhumatismale',
    'Ulcère gastroduodénal (2019)',
]
quartiers = ['Millionnaire', 'Dioulakro', 'Habitat', 'Fétiche', 'Dokui', 'Koko', 'Assabou', 'N\'Dotré']
contacts_noms = [
    'Koné Fatou', 'Traoré Aminata', 'Coulibaly Bréhima', 'Diabaté Salimata',
    'Bamba Karidja', 'Ouattara Mariam', 'Dembélé Kadiatou', 'Sanogo Pierre',
    'Fofana Fatoumata', 'Cissé Aminata', 'Konan Kouadio', 'Yao Bernard',
    'Nguessan Paul', 'Kouassi Brou', 'Brou Ama', 'Assi Jean',
    'Koffi Kouamé', 'Ahou Marc', 'Touré Seydou', 'Diomandé Moussa',
]
contacts_tels = [
    '0701234567', '0712345678', '0723456789', '0734567890', '0745678901',
    '0756789012', '0767890123', '0778901234', '0789012345', '0790123456',
    '0701234568', '0712345679', '0723456780', '0734567891', '0745678902',
    '0756789013', '0767890124', '0778901235', '0789012346', '0790123457',
]

all_patients = hommes + femmes
random.seed(42)
random.shuffle(all_patients)

created = 0
for i, (nom, prenoms, dob, lieu, tel, sexe, prof, ville, gs) in enumerate(all_patients):
    ass = random.choice(assurances + [None, None])
    prenom1 = prenoms.split()[0].lower()[:6]
    nom_slug = nom.lower().replace(' ', '').replace("'", '')
    email = f'{nom_slug}.{prenom1}{random.randint(10,99)}@gmail.com'

    p = Patient(
        nom=nom,
        prenoms=prenoms,
        date_naissance=dob,
        lieu_naissance=lieu,
        sexe=sexe,
        nationalite='Ivoirienne',
        profession=prof,
        telephone=tel,
        telephone2=f'0{random.randint(100000000, 799999999)}',
        email=email,
        adresse=f'Quartier {random.choice(quartiers)}, {ville}',
        ville=ville,
        groupe_sanguin=gs,
        allergies=allergies_list[i % len(allergies_list)],
        antecedents=antecedents_list[i % len(antecedents_list)],
        assurance=ass,
        numero_assurance=f'ASS{random.randint(10000,99999)}' if ass else '',
        date_expiration_assurance=date(2026, random.randint(1, 12), random.randint(1, 28)) if ass else None,
        contact_urgence_nom=contacts_noms[i],
        contact_urgence_telephone=contacts_tels[i],
        actif=True,
    )
    p.save()
    created += 1
    print(f'  [{p.code_patient}] {p.sexe} — {p.nom} {p.prenoms} ({p.age} ans) — {p.groupe_sanguin}')

print(f'\n{created} patients créés avec succès.')
