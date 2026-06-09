from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0015_add_registres_cpn_accouchement_postnatale_curatif'),
    ]

    operations = [
        migrations.AddField(
            model_name='rendezvous',
            name='date_confirme',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='rendezvous',
            name='date_en_attente',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='rendezvous',
            name='date_en_consultation',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='rendezvous',
            name='date_termine',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
