from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('consultations', '0004_ligneordonnance_produit'),
        ('medecins', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='ordonnance',
            name='medecin',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ordonnances_prescrites',
                to='medecins.medecin',
                verbose_name='Médecin prescripteur',
            ),
        ),
    ]
