import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0004_typecontrat_initial_data'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='HistoriqueEmploye',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type_changement', models.CharField(choices=[
                    ('creation', 'Création'), ('statut', 'Changement de statut'),
                    ('salaire', 'Changement de salaire'), ('service', 'Changement de service'),
                    ('contrat', 'Renouvellement de contrat'), ('autre', 'Modification'),
                ], max_length=20)),
                ('ancienne_valeur', models.CharField(blank=True, max_length=300)),
                ('nouvelle_valeur', models.CharField(blank=True, max_length=300)),
                ('note', models.CharField(blank=True, max_length=300)),
                ('date', models.DateTimeField(auto_now_add=True)),
                ('employe', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='historique', to='employer.employe')),
                ('fait_par', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Historique employé',
                'verbose_name_plural': 'Historique employés',
                'ordering': ['-date'],
            },
        ),
    ]
