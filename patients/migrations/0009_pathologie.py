from django.db import migrations, models


PATHOLOGIES_INITIALES = [
    # Paludisme
    ('Cas suspect de Paludisme', 'paludisme'),
    ('Cas suspect de Paludisme FE', 'paludisme'),
    ('Cas de Paludisme simple', 'paludisme'),
    ('Cas de Paludisme simple chez FE', 'paludisme'),
    ('Cas suspect de Paludisme grave référé', 'paludisme'),
    ('Cas suspect de Paludisme grave référée chez FE', 'paludisme'),
    ('Cas présumé de paludisme', 'paludisme'),
    ('Cas présumé de paludisme chez la FE', 'paludisme'),
    ('Cas de paludisme simple avec prescription de CTA (y compris femmes enceintes)', 'paludisme'),
    ('Cas de paludisme simple chez FE avec prescription de CTA', 'paludisme'),
    ('Cas de paludisme simple chez FE avec prescription de quinine', 'paludisme'),
    ('Cas suspect de paludisme avec prescription de CTA (présumé), y compris femme enceinte', 'paludisme'),
    ('Cas suspect de paludisme chez la femme enceinte avec prescription de CTA (présumé)', 'paludisme'),
    # Diarrhée
    ('Diarrhée aiguë sans déshydratation', 'diarrhee'),
    ('Diarrhée aiguë avec signes évidents de déshydratation', 'diarrhee'),
    ('Diarrhée aiguë avec déshydratation sévère', 'diarrhee'),
    ('Diarrhée aiguë sanglante', 'diarrhee'),
    ("Nombre d'enfants atteint de la diarrhée et ayant réçu une prescription de SRO + ZINC", 'diarrhee'),
    # IRA
    ('Pneumonie Simple (IRA basse)', 'ira'),
    ('Pneumonie grave (IRA basse)', 'ira'),
    ('Broncho-pneumonie (IRA basse)', 'ira'),
    ('Otite moyenne aigue (IRA haute)', 'ira'),
    ('Rhinopharyngite (IRA haute)', 'ira'),
    ('Angine (IRA haute)', 'ira'),
    ('Sinusite (IRA haute)', 'ira'),
    ('Laryngite (IRA haute)', 'ira'),
    ("Nombre d'enfants atteints de la pneumonie et ayant reçu une prescription d'antibiotique", 'ira'),
    # Maladies Tropicales Négligées
    ('Pian', 'mtns'),
    ('Bilharziose urinaire (CS)', 'mtns'),
    ('Trichiasis trachomateux (CS)', 'mtns'),
    ("Cas suspect d'hydrocèle", 'mtns'),
    ('Cas suspects de lymphodoedème', 'mtns'),
    ('Onchocercose', 'mtns'),
    # Maladies à Prévention Vaccinale
    ('Tétanos', 'vaccin'),
    ('Coqueluche', 'vaccin'),
    # Maladies Infectieuses
    ('Conjonctivite', 'infectieuse'),
    ('Fièvre Typhoïde / Salmonellose', 'infectieuse'),
    ('Fièvre Jaune', 'infectieuse'),
    ('Choléra', 'infectieuse'),
    ('Méningite', 'infectieuse'),
    ('Tuberculose (cas suspecte)', 'infectieuse'),
    ('Ulcère de burili (cas suspect)', 'infectieuse'),
    ('Varicelle', 'infectieuse'),
    ('Dermatose', 'infectieuse'),
    ('Zona', 'infectieuse'),
    ('Hépatite virale B', 'infectieuse'),
    ('Hépatite virale C', 'infectieuse'),
    ('Autres maladies infectieuses', 'infectieuse'),
    # Malnutrition
    ('Malnutrition modérée', 'malnutrition'),
    ('Malnutrition aiguë sévère référé', 'malnutrition'),
    # Maladies Chroniques
    ("HTA sans antécédent de HTA connu chez l'adulte, y compris FE", 'chronique'),
    ('HTA sans antécédent de HTA connu chez les FE (adulte)', 'chronique'),
    ("HTA avec antécédent de HTA connu chez l'adulte, y compris FE", 'chronique'),
    ('HTA avec antécédent de HTA connu chez les FE (adulte)', 'chronique'),
    ('Hyperglycémie sans antécédent de diabète connu', 'chronique'),
    ('Diabète gestationnel', 'chronique'),
    ('Asthme', 'chronique'),
    ('Drépanocytose', 'chronique'),
    ('Insuffisance rénale aiguë', 'chronique'),
    ('Anémie modérée', 'chronique'),
    ('Anémie grave', 'chronique'),
    ('Accident vasculaire cérébral (AVC)', 'chronique'),
    # Urgences Chirurgicales
    ('GEU', 'chirurgicale'),
    ('Fibrome utérin', 'chirurgicale'),
    ('Appendicite', 'chirurgicale'),
    ('Occlusion intestinale', 'chirurgicale'),
    ('Hernie', 'chirurgicale'),
    ('Péritonite', 'chirurgicale'),
    ('Goitre', 'chirurgicale'),
    # IST / MST
    ('Écoulement urétral masculin et/ou douleur et/ou prurit et/ou gêne intra urétral', 'ist'),
    ('Écoulement vaginal et/ou brûlure ou prurit et/ou malodeur vaginale', 'ist'),
    ('Ulcération génitale et/ou bubon masculin', 'ist'),
    ('Ulcération génitale et/ou bubon féminin', 'ist'),
    ('Douleur testiculaire', 'ist'),
    ('Douleurs abdominales basses (pelviennes) chez la femme', 'ist'),
    ('Conjonctivite du nouveau-né', 'ist'),
    ('Condylome (végétation vénériennes ou crêtes de coq) masculin', 'ist'),
    ('Condylome (végétation vénériennes ou crêtes de coq) féminin', 'ist'),
    # Traumatismes et Accidents
    ('Accidenté de la voie publique', 'traumatisme'),
    ('Brûlure', 'traumatisme'),
    ('Morsure de serpent', 'traumatisme'),
    ('Tentative de suicide', 'traumatisme'),
    ('Autres traumatismes', 'traumatisme'),
    # Maladies Psychiatriques
    ('Troubles psychiatriques', 'psychiatrique'),
    ('Retard psychomoteur', 'psychiatrique'),
    # Maladies à Déclaration Obligatoire
    ('Choléra cas suspecté', 'declaration'),
    ('Choléra cas investigué', 'declaration'),
    ('Méningite cas suspecté', 'declaration'),
    ('Méningite cas investigué', 'declaration'),
    ('Fièvre hémorragique cas suspecté', 'declaration'),
    ('Fièvre hémorragique cas investigué', 'declaration'),
    ('Paralysie flasque aiguë cas suspecté', 'declaration'),
    ('Paralysie flasque aiguë cas investigué', 'declaration'),
    ('Peste cas suspecté', 'declaration'),
    ('Peste cas investigué', 'declaration'),
    ('Diarrhées sanglantes cas suspecté', 'declaration'),
    ('Diarrhées sanglantes cas investigué', 'declaration'),
    ('Rougeole cas suspecté', 'declaration'),
    ('Rougeole cas investigué', 'declaration'),
    ('Fièvre jaune cas suspecté', 'declaration'),
    ('Fièvre jaune cas investigué', 'declaration'),
    # Autre
    ('Maladies indéterminées', 'autre'),
    ('Autres maladies non infectieuses', 'autre'),
]


def create_pathologies(apps, schema_editor):
    Pathologie = apps.get_model('patients', 'Pathologie')
    for nom, categorie in PATHOLOGIES_INITIALES:
        Pathologie.objects.get_or_create(nom=nom, defaults={'categorie': categorie})


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0008_merge_20260516_1422'),
    ]

    operations = [
        migrations.CreateModel(
            name='Pathologie',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=300, verbose_name='Nom')),
                ('categorie', models.CharField(
                    choices=[
                        ('paludisme',    'Paludisme'),
                        ('diarrhee',     'Diarrhée'),
                        ('ira',          'Infections Respiratoires Aigues (IRA)'),
                        ('mtns',         'Maladies Tropicales Négligées'),
                        ('vaccin',       'Maladies à Prévention Vaccinale'),
                        ('infectieuse',  'Maladies Infectieuses'),
                        ('malnutrition', 'Malnutrition'),
                        ('chronique',    'Maladies Chroniques'),
                        ('chirurgicale', 'Urgences Chirurgicales'),
                        ('ist',          'IST / MST'),
                        ('traumatisme',  'Traumatismes et Accidents'),
                        ('declaration',  'Maladies à Déclaration Obligatoire'),
                        ('psychiatrique','Maladies Psychiatriques'),
                        ('autre',        'Autre'),
                    ],
                    default='autre', max_length=20, verbose_name='Catégorie',
                )),
                ('description', models.TextField(blank=True, verbose_name='Description')),
                ('actif', models.BooleanField(default=True)),
                ('date_creation', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Pathologie',
                'ordering': ['categorie', 'nom'],
            },
        ),
        migrations.RunPython(create_pathologies, migrations.RunPython.noop),
    ]
