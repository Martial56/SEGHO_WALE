from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hospitalisation', '0002_batiment_chambre_v2'),
    ]

    operations = [
        # Supprimer le champ batiment
        migrations.RemoveField(
            model_name='chambre',
            name='batiment',
        ),

        # Mettre à jour les choix de type_chambre
        migrations.AlterField(
            model_name='chambre',
            name='type_chambre',
            field=models.CharField(
                choices=[
                    ('general',        'Général'),
                    ('semi_special',   'Semi-spécial'),
                    ('luxe',           'De luxe'),
                    ('super_luxe',     'Super luxe'),
                    ('suite',          'Suite'),
                    ('partage',        'Partage'),
                    ('soins_intensifs','Soins intensifs (ICU)'),
                    ('dialyse',        'Dialyse'),
                    ('salle_reveil',   'Salle de réveil'),
                ],
                default='general', max_length=20, verbose_name='Salle/Chambre Type',
            ),
        ),
    ]
