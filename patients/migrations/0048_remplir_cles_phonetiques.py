"""Remplit la table des clés phonétiques pour les fiches déjà en base.

La fonction qui réduit un mot à sa prononciation n'est pas recopiée ici. Elle
est appelée dans `patients.cles_phonetiques`, et c'est volontaire : figer une
copie ferait vivre deux versions de la même règle, celle de la migration et
celle du code, qui divergeraient au premier ajustement. Les clés écrites ici
n'ont pas à rester éternellement justes — elles se régénèrent toutes avec
`manage.py recalculer_doublons --cles`.

En contrepartie, ce module ne doit jamais être renommé ni supprimé. Si c'était
tout de même le cas, la migration passe sans rien écrire plutôt que de faire
échouer `migrate` sur une nouvelle installation, et le message dit quoi
lancer. Même remarque que pour `patients.dates_approximatives`.
"""

from django.db import migrations

LOT = 2000


def remplir(apps, schema_editor):
    try:
        from patients.cles_phonetiques import annee_de, cles
    except ImportError:
        print('\npatients.cles_phonetiques est introuvable : clés non écrites.')
        print("Lancez « manage.py recalculer_doublons --cles » après coup.")
        return

    Patient = apps.get_model('patients', 'Patient')
    ClePhonetique = apps.get_model('patients', 'ClePhonetique')

    lignes, ecrites, fiches = [], 0, 0
    for pk, nom, prenoms, naissance, centre_id in Patient.objects.values_list(
            'pk', 'nom', 'prenoms', 'date_naissance', 'centre_id').iterator(chunk_size=LOT):
        fiches += 1
        annee = annee_de(naissance)
        for cle in cles(nom, prenoms):
            lignes.append(ClePhonetique(patient_id=pk, cle=cle, annee=annee,
                                        centre_id=centre_id))
        if len(lignes) >= LOT:
            ClePhonetique.objects.bulk_create(lignes)
            ecrites += len(lignes)
            lignes = []
    if lignes:
        ClePhonetique.objects.bulk_create(lignes)
        ecrites += len(lignes)

    if fiches:
        print(f'\nClés phonétiques : {ecrites} lignes pour {fiches} fiches '
              f'({ecrites / fiches:.2f} par fiche).')


def vider(apps, schema_editor):
    """La table se régénère depuis les fiches : la vider ne perd rien."""
    apps.get_model('patients', 'ClePhonetique').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [('patients', '0047_patient_fusionne_dans_patient_masque_and_more')]

    operations = [migrations.RunPython(remplir, vider)]
