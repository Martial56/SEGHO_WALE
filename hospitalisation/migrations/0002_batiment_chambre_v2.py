from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('hospitalisation', '0001_initial'),
        ('medecins', '0001_initial'),
    ]

    operations = [
        # 1. Créer le modèle Batiment
        migrations.CreateModel(
            name='Batiment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=100, verbose_name='Nom')),
                ('description', models.TextField(blank=True, verbose_name='Description')),
            ],
            options={
                'verbose_name': 'Bâtiment',
                'verbose_name_plural': 'Bâtiments',
                'ordering': ['nom'],
            },
        ),

        # 2. Renommer numero → salle_no (conserve les données existantes)
        migrations.RenameField(
            model_name='chambre',
            old_name='numero',
            new_name='salle_no',
        ),

        # 3. Ajouter le champ nom (avec default '' pour les lignes existantes)
        migrations.AddField(
            model_name='chambre',
            name='nom',
            field=models.CharField(default='', max_length=100, verbose_name='Nom'),
            preserve_default=False,
        ),

        # 4. Ajouter batiment FK
        migrations.AddField(
            model_name='chambre',
            name='batiment',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='hospitalisation.batiment',
                verbose_name='Immeuble',
            ),
        ),

        # 5. Modifier type_chambre (ajout 'general', changement default)
        migrations.AlterField(
            model_name='chambre',
            name='type_chambre',
            field=models.CharField(
                choices=[
                    ('general',         'Général'),
                    ('simple',          'Simple'),
                    ('double',          'Double'),
                    ('vip',             'VIP'),
                    ('soins_intensifs', 'Soins intensifs'),
                    ('observation',     'Observation'),
                ],
                default='general', max_length=20, verbose_name='Salle/Chambre Type',
            ),
        ),

        # 6. Renommer disponible → statut
        migrations.RenameField(
            model_name='chambre',
            old_name='disponible',
            new_name='statut',
        ),
        migrations.AlterField(
            model_name='chambre',
            name='statut',
            field=models.BooleanField(default=True, verbose_name='Disponible'),
        ),

        # 7. Ajouter privé
        migrations.AddField(
            model_name='chambre',
            name='prive',
            field=models.BooleanField(default=False, verbose_name='Privé'),
        ),

        # 8. Ajouter genre
        migrations.AddField(
            model_name='chambre',
            name='genre',
            field=models.CharField(
                choices=[('unisexe', 'Unisexe'), ('masculin', 'Masculin'), ('feminin', 'Féminin')],
                default='unisexe', max_length=20, verbose_name='Genre',
            ),
        ),

        # 9. Équipements
        migrations.AddField(
            model_name='chambre', name='acces_internet',
            field=models.BooleanField(default=False, verbose_name='Accès Internet'),
        ),
        migrations.AddField(
            model_name='chambre', name='climatisation',
            field=models.BooleanField(default=False, verbose_name='Climatisation'),
        ),
        migrations.AddField(
            model_name='chambre', name='salle_bains_privee',
            field=models.BooleanField(default=False, verbose_name='Salle de bains privée'),
        ),
        migrations.AddField(
            model_name='chambre', name='television',
            field=models.BooleanField(default=False, verbose_name='Télévision'),
        ),
        migrations.AddField(
            model_name='chambre', name='telephone_chambre',
            field=models.BooleanField(default=False, verbose_name='Téléphone'),
        ),
        migrations.AddField(
            model_name='chambre', name='lit_visiteur',
            field=models.BooleanField(default=False, verbose_name='Lit de visiteur'),
        ),
        migrations.AddField(
            model_name='chambre', name='four_micro_onde',
            field=models.BooleanField(default=False, verbose_name='Four micro onde'),
        ),
        migrations.AddField(
            model_name='chambre', name='danger_biologique',
            field=models.BooleanField(default=False, verbose_name='Danger biologique'),
        ),
        migrations.AddField(
            model_name='chambre', name='refrigerateur',
            field=models.BooleanField(default=False, verbose_name='Réfrigérateur'),
        ),

        # 10. Mettre à jour verbose_name des champs existants
        migrations.AlterField(
            model_name='chambre',
            name='capacite',
            field=models.IntegerField(default=1, verbose_name='# Lits'),
        ),
        migrations.AlterField(
            model_name='chambre',
            name='prix_jour',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Prix/jour (FCFA)'),
        ),
        migrations.AlterField(
            model_name='chambre',
            name='description',
            field=models.TextField(blank=True, verbose_name='Notes'),
        ),

        # 11. Ordering
        migrations.AlterModelOptions(
            name='chambre',
            options={'ordering': ['salle_no'], 'verbose_name': 'Chambre'},
        ),
    ]
