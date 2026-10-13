"""Coche les dates de naissance que l'import a fabriquées à partir d'un âge.

Voir `patients.dates_approximatives` pour la règle : un jour/mois que porte une
part anormale des fiches d'un centre. Les dates elles-mêmes ne sont pas
touchées — on les étiquette, on ne les corrige pas : l'année reste la seule
information qu'elles portent, et elle est juste.

Le relevé se fait par centre, et le compte des fiches cochées est affiché :
sans cela, la migration passerait en silence sur des dizaines de milliers de
fiches sans qu'on sache lesquelles.
"""

from django.db import migrations


def marquer(apps, schema_editor):
    from patients.dates_approximatives import comptes_par_centre, jours_par_defaut

    Patient = apps.get_model('patients', 'Patient')
    # `objects` est ici un gestionnaire ordinaire : les modèles historiques
    # d'une migration n'héritent pas de CentreManager, donc rien n'est filtré
    # sur le centre actif — ce qui est bien ce qu'on veut.
    datees = Patient.objects.filter(date_naissance__isnull=False)

    lignes = [(centre_id, date.day, date.month) for centre_id, date
              in datees.values_list('centre_id', 'date_naissance').iterator(chunk_size=5000)]
    if not lignes:
        return

    totaux = {}
    for centre_id, _jour, _mois in lignes:
        totaux[centre_id] = totaux.get(centre_id, 0) + 1

    rapport = []
    for centre_id, comptes in comptes_par_centre(lignes).items():
        suspects = jours_par_defaut(comptes, totaux[centre_id])
        for jour, mois in sorted(suspects):
            coches = datees.filter(centre_id=centre_id,
                                   date_naissance__day=jour,
                                   date_naissance__month=mois
                                   ).update(date_naissance_approx=True)
            rapport.append(f'  centre {centre_id} — {jour:02d}/{mois:02d} : '
                           f'{coches} fiches ({100 * coches / totaux[centre_id]:.1f} %)')

    if rapport:
        print('\nDates de naissance marquées comme approximatives :')
        print('\n'.join(rapport))
    else:
        print('\nAucun jour/mois anormalement fréquent : rien de marqué.')


def demarquer(apps, schema_editor):
    """Le champ est le seul témoin : le remettre à faux rend la base à son état
    d'avant, sans perte — les dates n'ont jamais été modifiées."""
    Patient = apps.get_model('patients', 'Patient')
    Patient.objects.filter(date_naissance_approx=True).update(date_naissance_approx=False)


class Migration(migrations.Migration):

    dependencies = [('patients', '0044_patient_date_naissance_approx')]

    operations = [migrations.RunPython(marquer, demarquer)]
