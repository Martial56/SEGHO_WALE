import json
from pathlib import Path

import django.db.models.deletion
from django.db import migrations, models

# Le plan tiers de l'expert-comptable (comptabilite/data/plan_tiers.json, tiré
# de docs/PLAN TIERS.xlsx, export Sage 100 « Liste des tiers »). L'export ne
# donne pas le compte collectif : il est déduit du numéro (40110001 →
# 40110000) et se corrige à l'écran.
PLAN = Path(__file__).resolve().parent.parent / 'data' / 'plan_tiers.json'


def collectif_deduit(numero, comptes):
    """Copie figée de comptabilite.models.collectif_deduit."""
    meilleur = None
    for num, pk in comptes:
        racine = num.rstrip('0')
        if num != numero and racine and numero.startswith(racine)                 and (meilleur is None or len(racine) > meilleur[0]):
            meilleur = (len(racine), pk)
    return meilleur[1] if meilleur else None


def poser(apps, schema_editor):
    Compte = apps.get_model('comptabilite', 'Compte')
    Tiers = apps.get_model('comptabilite', 'Tiers')
    imputables = list(Compte.objects.filter(actif=True, totalisation=False).values_list('numero', 'pk'))
    existants = set(Tiers.objects.values_list('numero', flat=True))
    Tiers.objects.bulk_create([
        Tiers(numero=n, intitule=i, type=t, ville=v, compte_collectif_id=collectif_deduit(n, imputables))
        for n, i, t, v in json.loads(PLAN.read_text(encoding='utf-8')) if n not in existants])


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0017_journaux_expert'),
    ]

    operations = [
        migrations.CreateModel(
            name='Tiers',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero', models.CharField(max_length=17, unique=True, verbose_name='N° compte tiers')),
                ('intitule', models.CharField(max_length=200, verbose_name='Intitulé du tiers')),
                ('type', models.CharField(choices=[('client', 'Client'), ('fournisseur', 'Fournisseur'), ('salarie', 'Salarié'), ('autre', 'Autre')], max_length=12)),
                ('ville', models.CharField(blank=True, max_length=100, verbose_name='Code postal / ville')),
                ('actif', models.BooleanField(default=True)),
                ('compte_collectif', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='tiers', to='comptabilite.compte', verbose_name='Compte collectif')),
            ],
            options={
                'verbose_name': 'Compte tiers',
                'verbose_name_plural': 'Plan tiers',
                'ordering': ['numero'],
            },
        ),
        migrations.RunPython(poser, migrations.RunPython.noop),
    ]
