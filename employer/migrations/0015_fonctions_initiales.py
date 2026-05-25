from django.db import migrations

FONCTIONS = [
    # Direction & administration
    ('Directeur Général',            'DIR-GEN'),
    ('Directeur Médical',            'DIR-MED'),
    ('Administrateur',               'ADMIN'),
    ('Responsable RH',               'RH'),
    ('Comptable',                    'COMPTA'),
    ('Caissier(ère)',                'CAISSE'),
    ('Secrétaire Médical(e)',        'SEC-MED'),
    ('Agent d\'Accueil',             'ACCUEIL'),
    # Corps médical
    ('Médecin Généraliste',          'MED-GEN'),
    ('Médecin Spécialiste',         'MED-SPEC'),
    ('Médecin Chef',                 'MED-CHEF'),
    ('Chirurgien(ne)',               'CHIR'),
    ('Chirurgien(ne) Dentiste',      'DENTISTE'),
    ('Pédiatre',                     'PEDIATRE'),
    ('Gynécologue',                  'GYNECO'),
    ('Ophtalmologue',                'OPHTALMO'),
    ('Cardiologue',                  'CARDIO'),
    ('Dermatologue',                 'DERMATO'),
    ('Radiologue',                   'RADIO'),
    ('Anesthésiste',                 'ANESTH'),
    ('Psychologue',                  'PSYCHO'),
    # Paramédical
    ('Sage-Femme',                   'SAGE-F'),
    ('Infirmier(ère)',               'INFIRM'),
    ('Infirmier(ère) Chef',          'INF-CHEF'),
    ('Aide-Soignant(e)',             'AIDE-SOIG'),
    ('Kinésithérapeute',            'KINE'),
    ('Pharmacien(ne)',               'PHARMA'),
    ('Préparateur(rice) en Pharmacie', 'PREP-PHAR'),
    ('Laborantin(e)',                'LABO'),
    ('Technicien(ne) de Radiologie', 'TECH-RADIO'),
    ('Technicien(ne) de Laboratoire','TECH-LABO'),
    ('Nutritionniste',               'NUTRI'),
    ('Assistant(e) Social(e)',       'ASS-SOC'),
    # Support
    ('Agent de Sécurité',           'SECURITE'),
    ('Agent d\'Entretien',           'ENTRETIEN'),
    ('Chauffeur',                    'CHAUFFEUR'),
    ('Brancardier',                  'BRANCARD'),
    ('Technicien(ne) de Maintenance','TECH-MAINT'),
    ('Gestionnaire de Stock',        'GEST-STOCK'),
    ('Informaticien(ne)',            'INFORM'),
    ('Stagiaire',                    'STAGAIRE'),
]


def ajouter_fonctions(apps, schema_editor):
    Fonction = apps.get_model('employer', 'Fonction')
    for nom, code in FONCTIONS:
        Fonction.objects.get_or_create(code=code, defaults={'nom': nom})


def supprimer_fonctions(apps, schema_editor):
    Fonction = apps.get_model('employer', 'Fonction')
    codes = [c for _, c in FONCTIONS]
    Fonction.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0014_jourferie'),
    ]

    operations = [
        migrations.RunPython(ajouter_fonctions, supprimer_fonctions),
    ]
