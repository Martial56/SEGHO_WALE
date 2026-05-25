from django.db import migrations

CATEGORIES = {
    'direction': [
        'DIR-GEN', 'DIR-MED', 'ADMIN', 'RH', 'COMPTA', 'CAISSE',
        'SEC-MED', 'ACCUEIL', 'OP-SAISIE', 'GEST-PROJ', 'GEST-PROJ-ADJ',
        'GEST-DATA', 'INFORM',
    ],
    'medical': [
        'MED-GEN', 'MED-SPEC', 'MED-CHEF', 'CHIR', 'DENTISTE',
        'PEDIATRE', 'GYNECO', 'OPHTALMO', 'CARDIO', 'DERMATO',
        'RADIO', 'ANESTH', 'PSYCHO',
    ],
    'paramedical': [
        'SAGE-F', 'INFIRM', 'INF-CHEF', 'AIDE-SOIG', 'KINE',
        'PHARMA', 'PREP-PHAR', 'AUX-PHAR', 'LABO', 'TECH-RADIO',
        'TECH-LABO', 'NUTRI', 'ASS-SOC',
    ],
    'communautaire': [
        'AMD', 'CONS-COM',
    ],
    'support': [
        'SECURITE', 'ENTRETIEN', 'CHAUFFEUR', 'BRANCARD', 'TECH-MAINT',
        'GEST-STOCK', 'CHARG-CMD', 'TECH-SURF', 'GARDIEN', 'STAGAIRE',
    ],
}


def assigner_categories(apps, schema_editor):
    Fonction = apps.get_model('employer', 'Fonction')
    for categorie, codes in CATEGORIES.items():
        Fonction.objects.filter(code__in=codes).update(categorie=categorie)


def supprimer_categories(apps, schema_editor):
    Fonction = apps.get_model('employer', 'Fonction')
    Fonction.objects.all().update(categorie='')


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0018_fonction_categorie'),
    ]

    operations = [
        migrations.RunPython(assigner_categories, supprimer_categories),
    ]
