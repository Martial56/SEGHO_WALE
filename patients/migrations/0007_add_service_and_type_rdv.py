import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('medecins', '0001_initial'),
        ('patients', '0006_add_rdv_fields'),
    ]

    operations = [
        # service_id existe déjà en base — on met à jour uniquement l'état Django
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name='rendezvous',
                    name='service',
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='rendez_vous',
                        to='medecins.service',
                    ),
                ),
            ],
        ),
        # type_rdv est absent — on l'ajoute normalement
        migrations.AddField(
            model_name='rendezvous',
            name='type_rdv',
            field=models.CharField(
                choices=[
                    ('consultation', 'Consultation'),
                    ('controle', 'Contrôle'),
                    ('urgence', 'Urgence'),
                    ('examen', 'Examen'),
                    ('vaccination', 'Vaccination'),
                ],
                default='consultation',
                max_length=20,
            ),
        ),
    ]
