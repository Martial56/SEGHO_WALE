"""Rattache les factures et paiements à un centre.

Comme pour les soins, hospitalisations et rendez-vous, le centre n'est jamais
choisi arbitrairement : la facture le recopie depuis le patient (clé étrangère
obligatoire), et le paiement depuis sa facture (clé étrangère obligatoire elle
aussi). Aucun cas indécidable, aucune ligne orpheline possible. Le paiement est
traité après la facture, dans le même passage, pour que son `centre_id` source
soit déjà renseigné.

La liste des factures était jusqu'ici commune aux deux centres : chaque
utilisateur voyait toutes les factures, y compris celles de l'autre site.
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
        cur.execute(
            'UPDATE facturation_paiement SET centre_id = ('
            '  SELECT f.centre_id FROM facturation_facture f'
            '  WHERE f.id = facturation_paiement.facture_id'
            ') WHERE centre_id IS NULL'
        )


def detacher(apps, schema_editor):
    """Retour arrière : le rattachement repasse à NULL. Il se recalcule
    intégralement, aucune donnée n'est perdue."""
    with schema_editor.connection.cursor() as cur:
        cur.execute('UPDATE facturation_paiement SET centre_id = NULL')
        cur.execute('UPDATE facturation_facture SET centre_id = NULL')


class Migration(migrations.Migration):

    dependencies = [
        ('centres', '0004_rattacher_rendez_vous'),
        ('facturation', '0008_alter_facture_options_alter_paiement_options_and_more'),
    ]

    operations = [
        migrations.RunPython(rattacher, detacher),
    ]
