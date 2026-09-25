"""Coche « Espèces » sur les caisses qui n'ont encore aucun mode déclaré.

Le champ `modes_paiement` a d'abord signifié « vide = tous les modes acceptés ».
Il signifie maintenant « seuls les modes cochés sont proposés », et son défaut
est l'espèce. Les caisses créées avant ce changement sont vides : sans cette
reprise elles retomberaient sur `MODE_PAR_DEFAUT` à chaque lecture, ce qui donne
le bon résultat mais laisse leurs cases décochées à l'écran — l'utilisateur
verrait un réglage vide et un menu qui propose quand même l'espèce.
"""

from django.db import migrations


def cocher_especes(apps, schema_editor):
    Caisse = apps.get_model('facturation', 'Caisse')
    Caisse.objects.filter(modes_paiement='').update(modes_paiement='especes')


def vider(apps, schema_editor):
    Caisse = apps.get_model('facturation', 'Caisse')
    Caisse.objects.filter(modes_paiement='especes').update(modes_paiement='')


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0018_paiement_montant_recu_alter_caisse_modes_paiement'),
    ]

    operations = [
        migrations.RunPython(cocher_especes, vider),
    ]
