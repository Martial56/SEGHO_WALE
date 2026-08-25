"""Appui serveur du sélecteur de patient (templates/includes/_patient_picker.html)."""

from .models import Patient


def patient_affiche(form, champ='patient'):
    """Patient à peindre dans la carte du sélecteur, chargé sans filtre de centre.

    Le sélecteur remplit sa carte en interrogeant /patients/recherche/, qui ne
    renvoie que les dossiers du centre actif. Or les fiches qui pointent vers un
    patient — soins, procédures, hospitalisations — ne sont pas cloisonnées :
    elles restent visibles depuis n'importe quel centre. Dès que le patient
    relevait de l'autre site, la recherche ne trouvait rien et le champ restait
    obstinément vide en modification, sans le moindre message.

    En passant l'objet au gabarit, la carte est écrite côté serveur : plus
    d'appel réseau, et le dossier s'affiche quel que soit le centre. Le recours
    à `all_objects` est délibéré — c'est précisément le dossier hors périmètre
    qu'il s'agit de pouvoir montrer.

    Renvoie None quand aucun patient n'est sélectionné : le gabarit retombe
    alors sur le champ de recherche, comme en création.
    """
    try:
        pk = form[champ].value()
    except KeyError:
        return None
    if not pk:
        return None
    return Patient.all_objects.select_related('assurance').filter(pk=pk).first()
