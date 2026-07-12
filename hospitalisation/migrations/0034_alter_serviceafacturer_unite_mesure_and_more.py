import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hospitalisation', '0033_add_can_ajouter_soin_permission'),
        ('stock', '0012_categorieunitemesure_unitemesure'),
    ]

    operations = [
        migrations.AlterField(
            model_name='serviceafacturer',
            name='unite_mesure',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='stock.unitemesure', verbose_name='Unité de mesure'),
        ),
        migrations.AlterField(
            model_name='visiteinfirmiere',
            name='unite_mesure',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='stock.unitemesure', verbose_name='Unité de mesure'),
        ),
    ]
