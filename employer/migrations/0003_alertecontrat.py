import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0002_employe_date_embauche_required'),
    ]

    operations = [
        migrations.CreateModel(
            name='AlerteContrat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('echeance', models.CharField(choices=[('2_mois', '2 mois'), ('1_mois', '1 mois')], max_length=10)),
                ('date_fin_contrat', models.DateField()),
                ('lue', models.BooleanField(default=False)),
                ('cree_le', models.DateTimeField(auto_now_add=True)),
                ('employe', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='alertes_contrat',
                    to='employer.employe',
                )),
            ],
            options={
                'verbose_name': 'Alerte contrat',
                'verbose_name_plural': 'Alertes contrat',
                'ordering': ['-cree_le'],
                'unique_together': {('employe', 'echeance')},
            },
        ),
    ]
