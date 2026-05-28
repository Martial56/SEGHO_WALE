import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('medecins', '0001_initial'),
        ('patients', '0006_add_rdv_fields'),
    ]

    operations = [
        # service est géré par 0003_replace_type_rdv_with_service_fk (état uniquement).
        # Ici on ne fait rien pour service (ni DB ni état).
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[],
        ),
        # type_rdv : retiré de l'état par 0003_replace — on le remet dans l'état.
        # La colonne DB est déjà présente (ajoutée lors de la première exécution de 0007).
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
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
            ],
        ),
    ]
