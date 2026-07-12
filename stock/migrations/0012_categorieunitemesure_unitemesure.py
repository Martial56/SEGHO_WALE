import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0011_fiche_besoins_pharmacie_optional'),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS stock_unitemesure;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='CategorieUniteMesure',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('nom', models.CharField(max_length=100, unique=True, verbose_name='Nom')),
                    ],
                    options={
                        'verbose_name': "Catégorie d'unité de mesure",
                        'verbose_name_plural': "Catégories d'unités de mesure",
                        'ordering': ['nom'],
                    },
                ),
                migrations.CreateModel(
                    name='UniteMesure',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('nom', models.CharField(max_length=100, unique=True, verbose_name='Nom')),
                        ('code', models.CharField(max_length=20, unique=True, verbose_name='Abréviation')),
                        ('type_unite', models.CharField(choices=[('pgumr', "Plus grande que l'unité de mesure de référence"), ('umrc', 'Unité de mesure de référence pour cette catégorie'), ('ppumr', "Plus petite que l'unité de mesure de référence")], default='umrc', max_length=10, verbose_name='Type')),
                        ('ratio', models.DecimalField(decimal_places=6, default=1, max_digits=12, verbose_name='Ratio')),
                        ('precision_arrondi', models.DecimalField(decimal_places=5, default=0.01, max_digits=8, verbose_name="Précision d'arrondi")),
                        ('actif', models.BooleanField(default=True, verbose_name='Actif')),
                        ('categorie', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='unites', to='stock.categorieunitemesure', verbose_name='Catégorie')),
                    ],
                    options={
                        'verbose_name': 'Unité de mesure',
                        'verbose_name_plural': 'Unités de mesure',
                        'ordering': ['nom'],
                    },
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE services_categorieunitemesure RENAME TO stock_categorieunitemesure;",
                    reverse_sql="ALTER TABLE stock_categorieunitemesure RENAME TO services_categorieunitemesure;",
                ),
                migrations.RunSQL(
                    sql="ALTER TABLE services_unitemesure RENAME TO stock_unitemesure;",
                    reverse_sql="ALTER TABLE stock_unitemesure RENAME TO services_unitemesure;",
                ),
            ],
        ),
    ]
