from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0002_update_visites_saf_articleservice'),
        ('patients', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='facture',
            name='rendez_vous',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='factures',
                to='patients.rendezvous',
                verbose_name='Rendez-vous',
            ),
        ),
    ]
