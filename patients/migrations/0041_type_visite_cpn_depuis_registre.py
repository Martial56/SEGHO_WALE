"""Pose `RendezVous.cpn_type_visite` d'après le registre CPN.

Le rapport maternité compte les CPN par cette clé étrangère. Certains chemins
d'enregistrement n'écrivaient que le JSON du registre : l'identifiant du
`gynecologie.TypeVisite` y était, la clé étrangère restait vide.

Les anciennes valeurs de la fiche patients ne sont pas converties :
« 1ère visite » voulait dire première venue au centre WALÉ, quel que soit le
rang de la CPN, et « Visite de suivi » ne dit pas le rang non plus.
"""
from django.db import migrations


def remplir(apps, schema_editor):
    RegistreCPN = apps.get_model('patients', 'RegistreCPN')
    RendezVous = apps.get_model('patients', 'RendezVous')
    TypeVisite = apps.get_model('gynecologie', 'TypeVisite')
    existants = set(TypeVisite.objects.values_list('pk', flat=True))

    for reg in RegistreCPN.objects.filter(rdv__cpn_type_visite__isnull=True):
        valeur = str((reg.donnees or {}).get('cpn_type_visite') or '').strip()
        if valeur.isdigit() and int(valeur) in existants:
            RendezVous.objects.filter(pk=reg.rdv_id).update(cpn_type_visite_id=int(valeur))


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0040_alter_rendezvous_options'),
        ('gynecologie', '0002_seed_types_visite'),
    ]

    operations = [
        migrations.RunPython(remplir, migrations.RunPython.noop),
    ]
