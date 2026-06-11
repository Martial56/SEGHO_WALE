from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0008_set_db_tables'),
    ]

    operations = [
        # 1. Ajout du champ nb_jours_ouvres sur Conge
        migrations.AddField(
            model_name='conge',
            name='nb_jours_ouvres',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text='Jours ouvrés décomptés du solde',
            ),
        ),
        # 2. Mise à jour des choix de type_conge
        migrations.AlterField(
            model_name='conge',
            name='type_conge',
            field=models.CharField(
                choices=[
                    ('annuel',           'Congé annuel'),
                    ('maladie',          'Congé maladie'),
                    ('maternite',        'Congé maternité'),
                    ('paternite',        'Congé paternité'),
                    ('exceptionnel',     'Congé exceptionnel'),
                    ('mariage_employe',  'Mariage (employé)'),
                    ('mariage_enfant',   'Mariage (enfant)'),
                    ('deces_conjoint',   'Décès conjoint'),
                    ('deces_enfant',     'Décès enfant'),
                    ('deces_parent',     'Décès parent/beau-parent'),
                    ('deces_frere_soeur','Décès frère/sœur'),
                    ('naissance_enfant', 'Naissance enfant (père)'),
                    ('sans_solde',       'Congé sans solde'),
                ],
                max_length=20,
            ),
        ),
        # 3. Création du modèle SoldeConge
        migrations.CreateModel(
            name='SoldeConge',
            fields=[
                ('id',            models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('annee',         models.PositiveSmallIntegerField()),
                ('quota',         models.DecimalField(decimal_places=1, default=0, max_digits=5)),
                ('jours_pris',    models.DecimalField(decimal_places=1, default=0, max_digits=5)),
                ('jours_reporter',models.DecimalField(decimal_places=1, default=0, max_digits=5)),
                ('note',          models.TextField(blank=True)),
                ('mis_a_jour_le', models.DateTimeField(auto_now=True)),
                ('employe',       models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='soldes_conge',
                    to='employer.Employe',
                )),
            ],
            options={
                'verbose_name':          'Solde de congé',
                'verbose_name_plural':   'Soldes de congé',
                'db_table':              'ressources_humaines_soldeconge',
                'ordering':              ['-annee'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='soldeconge',
            unique_together={('employe', 'annee')},
        ),
    ]
