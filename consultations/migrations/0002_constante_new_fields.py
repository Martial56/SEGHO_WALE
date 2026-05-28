from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('consultations', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='constante',
            name='tension_systolique_droite',
            field=models.IntegerField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='constante',
            name='tension_diastolique_droite',
            field=models.IntegerField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='constante',
            name='frequence_respiratoire',
            field=models.IntegerField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='constante',
            name='albumine',
            field=models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='constante',
            name='perimetre_brachial',
            field=models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='constante',
            name='niveau_douleur',
            field=models.IntegerField(null=True, blank=True),
        ),
    ]
