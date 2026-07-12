import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('medecins', '0010_service_medecine_generale_gynecologie'),
        ('patients', '0017_merge_0016'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='rendezvous',
            name='service',
        ),
        migrations.RenameField(
            model_name='rendezvous',
            old_name='departement',
            new_name='departement_code_old',
        ),
        migrations.AlterField(
            model_name='rendezvous',
            name='departement_code_old',
            field=models.CharField(max_length=30, blank=True, default=''),
        ),
        migrations.AddField(
            model_name='rendezvous',
            name='departement',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='rendez_vous', to='medecins.service', verbose_name='Service'),
        ),
    ]
