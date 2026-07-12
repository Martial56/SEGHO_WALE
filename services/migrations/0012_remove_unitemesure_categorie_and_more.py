import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hospitalisation', '0034_alter_serviceafacturer_unite_mesure_and_more'),
        ('services', '0011_alter_articleservice_reference_interne'),
        ('stock', '0012_categorieunitemesure_unitemesure'),
    ]

    operations = [
        migrations.AlterField(
            model_name='articleservice',
            name='unite_achat',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='articles_ua', to='stock.unitemesure', verbose_name="Unité d'achat"),
        ),
        migrations.AlterField(
            model_name='lignefournisseurarticle',
            name='unite_mesure',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='stock.unitemesure', verbose_name='Unité de mesure'),
        ),
        migrations.AlterField(
            model_name='conditionnementarticle',
            name='unite_mesure',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='stock.unitemesure', verbose_name='Unité de mesure'),
        ),
        migrations.AlterField(
            model_name='articleservice',
            name='unite_mesure',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='articles_um', to='stock.unitemesure', verbose_name='Unité de mesure'),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='unitemesure',
                    name='categorie',
                ),
                migrations.DeleteModel(
                    name='CategorieUniteMesure',
                ),
                migrations.DeleteModel(
                    name='UniteMesure',
                ),
            ],
            database_operations=[],
        ),
    ]
