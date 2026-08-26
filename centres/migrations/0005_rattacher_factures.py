"""Rattache les factures à un centre, recopié depuis le patient.

Même règle que pour les soins, les hospitalisations et les rendez-vous : le
centre n'est jamais choisi, il vient du patient. `Facture.patient` est une clé
étrangère obligatoire, il n'y a donc aucun cas indécidable.

La comptabilité était jusqu'ici entièrement commune : un utilisateur de
Toumbokro voyait les 479 factures nominatives de Yamoussoukro. Les lignes de
facture et les paiements n'ont pas de centre propre — ils pendent de la facture
en cascade et suivent donc son cloisonnement.
"""

from django.db import migrations


def rattacher(apps, schema_editor):
    Centre = apps.get_model('centres', 'Centre')
    if not Centre.objects.exists():
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute(
            'UPDATE facturation_facture SET centre_id = ('
            '  SELECT p.centre_id FROM patients_patient p'
            '  WHERE p.id = facturation_facture.patient_id'
            ') WHERE centre_id IS NULL'
        )


def detacher(apps, schema_editor):
    """Retour arrière : le rattachement repasse à NULL et se recalcule
    intégralement. Aucun montant n'est touché."""
    with schema_editor.connection.cursor() as cur:
        cur.execute('UPDATE facturation_facture SET centre_id = NULL')


class Migration(migrations.Migration):

    dependencies = [
        ('centres', '0004_rattacher_rendez_vous'),
        ('facturation', '0008_alter_facture_options_alter_facture_managers_and_more'),
    ]

    operations = [
        migrations.RunPython(rattacher, detacher),
    ]
