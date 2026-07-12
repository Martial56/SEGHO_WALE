import django.db.models.deletion
from django.db import migrations, models


def migrate_unite_mesure_data(apps, schema_editor):
    Produit = apps.get_model('stock', 'Produit')
    UniteMesure = apps.get_model('stock', 'UniteMesure')
    default_unite = UniteMesure.objects.filter(nom__iexact='Unité').first()
    for p in Produit.objects.all():
        match = UniteMesure.objects.filter(nom__iexact=p.unite_mesure_texte).first()
        p.unite_mesure = match or default_unite
        p.save(update_fields=['unite_mesure'])


def reverse_unite_mesure_data(apps, schema_editor):
    Produit = apps.get_model('stock', 'Produit')
    for p in Produit.objects.exclude(unite_mesure__isnull=True):
        p.unite_mesure_texte = p.unite_mesure.nom.lower()
        p.save(update_fields=['unite_mesure_texte'])


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0012_categorieunitemesure_unitemesure'),
    ]

    operations = [
        migrations.RenameField(
            model_name='produit',
            old_name='unite_mesure',
            new_name='unite_mesure_texte',
        ),
        migrations.AddField(
            model_name='produit',
            name='unite_mesure',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                to='stock.unitemesure', verbose_name='Unité de mesure',
            ),
        ),
        migrations.RunPython(migrate_unite_mesure_data, reverse_unite_mesure_data),
        migrations.RemoveField(
            model_name='produit',
            name='unite_mesure_texte',
        ),
    ]
