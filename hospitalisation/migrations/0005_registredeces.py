from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('hospitalisation', '0004_chambre_remove_service'),
        ('medecins', '0001_initial'),
        ('patients', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='RegistreDeces',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code',         models.CharField(editable=False, max_length=20, unique=True)),
                ('date_deces',   models.DateField(verbose_name='Date de décès')),
                ('raison_deces', models.TextField(verbose_name='Raison du décès')),
                ('remarques',    models.TextField(blank=True, verbose_name='Remarques')),
                ('statut',       models.CharField(
                    choices=[('brouillon', 'Brouillon'), ('termine', 'Terminé')],
                    default='brouillon', max_length=20, verbose_name='Statut',
                )),
                ('cree_le',      models.DateTimeField(auto_now_add=True)),
                ('patient', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='deces',
                    to='patients.patient',
                    verbose_name='Patient',
                )),
                ('hospitalisation', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='hospitalisation.hospitalisation',
                    verbose_name='Hospitalisation',
                )),
                ('medecin', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='medecins.medecin',
                    verbose_name='Docteur',
                )),
            ],
            options={
                'verbose_name': 'Registre des décès',
                'verbose_name_plural': 'Registre des décès',
                'ordering': ['-date_deces'],
            },
        ),
    ]
