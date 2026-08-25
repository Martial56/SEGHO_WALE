"""Rattache à un centre les soins, procédures, hospitalisations et décès.

Le centre n'est jamais choisi arbitrairement : il est recopié depuis le patient,
qui en porte un depuis que `patients.Patient` est un ModeleCentre. Les quatre
tables ont un patient obligatoire, il n'y a donc aucun cas indécidable et aucune
ligne ne peut rester orpheline.

Ces quatre modèles étaient les derniers de leurs modules à ne pas être
cloisonnés : la liste des hospitalisations compensait par un filtre écrit à la
main dans sa vue, qui ne protégeait qu'elle — la fiche restait consultable
depuis l'autre centre. Les soins, les procédures et le registre des décès
n'avaient rien du tout. Porté par le modèle, le filtre s'applique désormais
partout : listes, fiches, formulaires, exports.
"""

from django.db import migrations


# (table, colonne portant le patient)
TABLES = [
    ('soins_soin',                      'patient_id'),
    ('soins_proceduresoin',             'patient_id'),
    ('hospitalisation_hospitalisation', 'patient_id'),
    ('hospitalisation_registredeces',   'patient_id'),
]


def rattacher(apps, schema_editor):
    Centre = apps.get_model('centres', 'Centre')
    if not Centre.objects.exists():
        return
    with schema_editor.connection.cursor() as cur:
        for table, colonne in TABLES:
            cur.execute(
                'UPDATE {t} SET centre_id = ('
                '  SELECT p.centre_id FROM patients_patient p WHERE p.id = {t}.{c}'
                ') WHERE centre_id IS NULL'.format(t=table, c=colonne)
            )


def detacher(apps, schema_editor):
    """Retour arrière : les colonnes repassent à NULL. Aucune donnée n'est
    perdue, seul le rattachement l'est — il se recalcule intégralement."""
    with schema_editor.connection.cursor() as cur:
        for table, _ in TABLES:
            cur.execute('UPDATE {t} SET centre_id = NULL'.format(t=table))


class Migration(migrations.Migration):

    dependencies = [
        ('centres', '0002_creer_centres_initiaux'),
        ('soins', '0011_alter_proceduresoin_options_alter_soin_options_and_more'),
        ('hospitalisation', '0037_alter_hospitalisation_options_and_more'),
    ]

    operations = [
        migrations.RunPython(rattacher, detacher),
    ]
