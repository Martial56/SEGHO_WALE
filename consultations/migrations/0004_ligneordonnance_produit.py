import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('consultations', '0003_ordonnance_nullable_consultation_add_patient'),
        ('stock', '0011_fiche_besoins_pharmacie_optional'),
    ]

    operations = [
        migrations.AddField(
            model_name='ligneordonnance',
            name='produit',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='lignes_ordonnance',
                to='stock.produit',
            ),
        ),
    ]
