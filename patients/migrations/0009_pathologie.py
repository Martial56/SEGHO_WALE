from django.db import migrations, models


# Le catalogue des pathologies n'est plus prérempli : la table est créée vide
# et chaque établissement la remplit lui-même (saisie manuelle ou bouton
# Export/Import de la page Pathologies).


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
    ]
