"""Résultats d'examens rattachés à une consultation (rendez-vous).

Partagé par les deux fiches de consultation — médecine générale
(patients/rendez_vous_form.html) et gynécologie (gynecologie/rdv_form.html) —
qui affichent le même onglet « Résultats d'examens ».
"""
from django.db.models import Prefetch


def demandes_de_consultation(rdv):
    """Les demandes d'examens faites depuis cette consultation, chacune avec
    ses analyses reçues et leurs paramètres. `nb_anormaux` est posé sur chaque
    analyse pour l'en-tête de l'onglet."""
    if rdv is None or not rdv.pk:
        return []
    from .models import AnalyseLaboratoire
    demandes = list(
        rdv.demandes_examens.prefetch_related(
            'lignes',
            Prefetch('analyses',
                     queryset=AnalyseLaboratoire.objects.prefetch_related('resultats')
                     .order_by('-date_resultat')),
        ).order_by('-date_creation')
    )
    for demande in demandes:
        for analyse in demande.analyses.all():
            analyse.nb_anormaux = sum(1 for r in analyse.resultats.all() if r.anormal)
    return demandes


def nb_non_ouverts(demandes):
    """Résultats de ces demandes que le médecin n'a pas encore ouverts."""
    return sum(1 for d in demandes for a in d.analyses.all() if a.vu_le is None)


def compte_du_medecin(medecin):
    """Le compte utilisateur d'un médecin : le sien, à défaut celui de sa
    fiche employé."""
    if medecin is None:
        return None
    if medecin.user_id:
        return medecin.user
    employe = getattr(medecin, 'employe', None)
    return getattr(employe, 'user', None)


def destinataire_de(demande):
    """Qui prévenir quand le résultat de cette demande arrive : le médecin
    prescripteur, à défaut celui de la consultation d'où elle a été faite."""
    if demande is None:
        return None
    compte = compte_du_medecin(demande.medecin_prescripteur)
    if compte is None and demande.rendez_vous_id:
        compte = compte_du_medecin(demande.rendez_vous.medecin)
    return compte


def marquer_vus(analyses, user):
    """Marque comme ouverts les résultats que `user` avait à lire.

    Un résultat adressé à un médecin n'est « ouvert » que par lui : une
    infirmière qui consulte le dossier ne doit pas éteindre son alerte.
    Un résultat sans destinataire (prescripteur sans compte utilisateur) est
    ouvert par le premier qui le lit. On exigeait jusqu'ici un compte relié à
    une fiche médecin, mais aucun compte ne l'était : l'onglet restait rouge
    après lecture, sans que personne ne puisse l'éteindre.
    Retourne le nombre de résultats marqués."""
    from django.db.models import Q
    from django.utils import timezone
    from .models import AnalyseLaboratoire
    pks = [a.pk for a in analyses if a.vu_le is None]
    if not pks:
        return 0
    return (AnalyseLaboratoire.objects
            .filter(pk__in=pks, vu_le__isnull=True)
            .filter(Q(destinataire=user) | Q(destinataire__isnull=True))
            .update(vu_le=timezone.now()))
