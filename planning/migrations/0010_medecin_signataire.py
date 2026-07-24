from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0009_gabaritaffectation_note'),
    ]

    operations = [
        migrations.CreateModel(
            name='MedecinSignataire',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=200)),
                ('actif', models.BooleanField(default=True)),
                ('ordre', models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                'verbose_name': 'Médecin signataire',
                'verbose_name_plural': 'Médecins signataires',
                'ordering': ['ordre', 'nom'],
            },
        ),
        migrations.AddField(
            model_name='planningconfig',
            name='fonction_signataire',
            field=models.CharField(
                choices=[
                    ('directeur_medical', 'Directeur Médical'),
                    ('directrice_medicale', 'Directrice Médicale'),
                    ('directeur_medical_adjoint', 'Directeur Médical Adjoint'),
                    ('directrice_medicale_adjointe', 'Directrice Médicale Adjointe'),
                ],
                default='directrice_medicale_adjointe',
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name='planningconfig',
            name='medecin_defaut',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='planning.medecinsignataire',
            ),
        ),
        migrations.AddField(
            model_name='planninghebdomadaire',
            name='signataire_new',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='plannings',
                to='planning.medecinsignataire',
            ),
        ),
    ]
