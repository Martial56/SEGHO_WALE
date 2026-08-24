"""Rattache les rendez-vous à un centre, en le recopiant depuis le patient.

Comme pour les soins et les hospitalisations, le centre n'est jamais choisi :
il vient du patient, dont le rendez-vous dépend par une clé étrangère
obligatoire. Aucun cas indécidable, aucune ligne orpheline possible.

Le carnet de rendez-vous était jusqu'ici commun aux deux centres : chaque
utilisateur voyait les 521 rendez-vous, y compris ceux de l'autre site.
"""

from django.db import migrations


def rattacher(apps, schema_editor):
    Centre = apps.get_model('centres', 'Centre')
    if not Centre.objects.exists():
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute(
            'UPDATE patients_rendezvous SET centre_id = ('
            '  SELECT p.centre_id FROM patients_patient p'
            '  WHERE p.id = patients_rendezvous.patient_id'
            ') WHERE centre_id IS NULL'
        )


def detacher(apps, schema_editor):
    """Retour arrière : le rattachement repasse à NULL. Il se recalcule
    intégralement, aucune donnée n'est perdue."""
    with schema_editor.connection.cursor() as cur:
        cur.execute('UPDATE patients_rendezvous SET centre_id = NULL')


class Migration(migrations.Migration):

    dependencies = [
        ('centres', '0003_rattacher_soins_et_hospitalisations'),
        ('patients', '0038_alter_rendezvous_options_alter_rendezvous_managers_and_more'),
    ]

    operations = [
        migrations.RunPython(rattacher, detacher),
    ]
