"""Supprimer définitivement une fiche — le seul geste irréversible du menu.

Tout le reste se défait : un masquage se réaffiche, une fusion s'annule, une
paire écartée se reprend. Ici, non. D'où les trois verrous :

* la fiche doit être **retirée** — masquée, ou versée dans une autre. Un
  dossier ouvert ne se supprime pas depuis cet écran ;
* elle ne doit porter **aucune donnée** : ni rendez-vous, ni facture, ni
  analyse. Le contrôle est refait ici, au moment de supprimer, et pas
  seulement à l'affichage du bouton — entre les deux, quelqu'un a pu
  rattacher quelque chose ;
* c'est un super-utilisateur qui décide, et il tape le code de la fiche.

Ce qui part avec elle : ses clés phonétiques, les paires relevées qui la
citent, les décisions prises sur ces paires. Ce sont des vues sur la fiche,
elles n'ont plus d'objet sans elle.

Ce qui reste : une `SuppressionPatient` avec la copie complète et le journal
recopié, le journal des fusions avec sa copie à lui, et — c'est le point
délicat — **la redirection de l'ancien code**. Des cartes et des reçus
imprimés le portent. Il ne peut plus passer par la fiche, qui n'existe plus :
il passe par `FusionPatient.code_absorbee`, et les fiches qui pointaient sur
celle-ci sont reportées sur sa remplaçante avant l'effacement, pour que la
chaîne ne se coupe nulle part.
"""

from django.db import transaction

from .liens_patient import comptes, oublier_les_totaux


class SuppressionRefusee(Exception):
    """Ce que la suppression refuse de faire, en une phrase lisible."""


def etat(fiche):
    """« fusionnee », « masquee », ou '' pour un dossier ouvert."""
    if fiche.fusionne_dans_id:
        return 'fusionnee'
    if fiche.masque:
        return 'masquee'
    return ''


def obstacles(fiche):
    """Les raisons de refuser, en clair. Liste vide : on peut supprimer."""
    raisons = []
    if not etat(fiche):
        raisons.append("C'est un dossier ouvert : seule une fiche masquée ou "
                       "versée dans une autre peut être supprimée.")
    porte = {libelle: n for libelle, n in comptes([fiche.pk])[fiche.pk].items() if n}
    if porte:
        detail = ', '.join(f'{n} {libelle.lower()}' for libelle, n in porte.items())
        raisons.append(f'Elle porte encore {detail} : il faut la fusionner.')
    if _renvois(fiche).exists() and fiche.remplacee_par is None:
        # Supprimer celle-ci laisserait les autres pointer dans le vide, et
        # leur propre ancien code ne mènerait plus nulle part.
        raisons.append("D'autres fiches renvoient vers celle-ci, et elle ne "
                       "renvoie elle-même nulle part.")
    return raisons


def _renvois(fiche):
    """Les fiches qui pointent sur celle-ci — absorbées ou masquées."""
    from django.db.models import Q
    from .models import Patient
    return Patient.all_objects.filter(
        Q(fusionne_dans=fiche) | Q(doublon_de=fiche))


def ce_qui_part(fiche):
    """[(libellé, nombre)] : ce que la suppression emporte, pour l'écran.

    Montré avant de demander le code. « Supprimer » ne veut rien dire tant
    qu'on ne sait pas ce qui part avec.
    """
    from .models import ChoixFicheGardee, ClePhonetique, DoublonPaire, PaireEcartee
    from django.db.models import Q

    paires = DoublonPaire.all_objects.filter(
        Q(patient_a=fiche) | Q(patient_b=fiche)).count()
    ecartees = PaireEcartee.all_objects.filter(
        Q(patient_a=fiche) | Q(patient_b=fiche)).count()
    lignes = [
        ('Clés phonétiques', ClePhonetique.all_objects.filter(patient=fiche).count()),
        ('Rapprochements relevés', paires),
        ('Paires écartées à la main', ecartees),
        ('Désignations « fiche à garder »',
         ChoixFicheGardee.all_objects.filter(patient=fiche).count()),
        ('Lignes de journal (recopiées puis effacées)', _traces(fiche).count()),
    ]
    return [(libelle, n) for libelle, n in lignes if n]


def _traces(fiche):
    from core.models import LogActivite
    from .fusion import _type_patient
    return (LogActivite.objects.filter(content_type=_type_patient(),
                                       object_id=fiche.pk)
            .select_related('user').order_by('-date'))


def supprimer(fiche, utilisateur):
    """Efface la fiche et rend la trace écrite. Lève `SuppressionRefusee`.

    Le verrou partagé, comme la fusion : un recalcul complet qui tourne est
    en train de réécrire les paires du centre, et il en écrirait pour une
    fiche qu'on efface.
    """
    from .doublons_recalcul import RecalculDejaEnCours, verrou
    try:
        with verrou(exclusif=False):
            return _supprimer(fiche, utilisateur)
    except RecalculDejaEnCours:
        raise SuppressionRefusee(
            'Un recalcul complet des doublons est en cours : réessayez dans '
            'un moment.')


@transaction.atomic
def _supprimer(fiche, utilisateur):
    """Les contrôles sont refaits ici : c'est le dernier endroit où l'état de
    la base est celui qu'on supprime."""
    refus = obstacles(fiche)
    if refus:
        raise SuppressionRefusee(' '.join(refus))

    trace = _ecrire_la_trace(fiche, utilisateur)
    _figer_le_journal_des_fusions(fiche)
    _reporter_les_renvois(fiche)
    _traces(fiche).delete()
    fiche.delete()
    # Les totaux gardés une minute pour le filtre de l'écran : une fiche
    # supprimée ne doit pas continuer d'y figurer.
    oublier_les_totaux()
    return trace


def _ecrire_la_trace(fiche, utilisateur):
    from .fusion import _en_json, _lire
    from .models import SuppressionPatient

    remplacante = fiche.remplacee_par
    return SuppressionPatient.all_objects.create(
        centre_id=fiche.centre_id,
        code_patient=fiche.code_patient,
        ancien_identifiant=fiche.ancien_identifiant or '',
        nom=fiche.nom, prenoms=fiche.prenoms,
        etat=etat(fiche),
        code_remplacante=remplacante.code_patient if remplacante else '',
        copie={f.name: _en_json(f, _lire(fiche, f))
               for f in fiche._meta.concrete_fields},
        journal=[{'date': trace.date.isoformat(),
                  'type': trace.type, 'code': trace.code,
                  'message': trace.message,
                  'utilisateur': trace.user.username if trace.user else ''}
                 for trace in _traces(fiche)],
        utilisateur=(utilisateur if utilisateur
                     and utilisateur.is_authenticated else None))


def _figer_le_journal_des_fusions(fiche):
    """Recopie les repères de la fiche dans les fusions qui la citent.

    Ils y sont déjà, posés à la fusion ; on les repose avant l'effacement
    parce que c'est le dernier moment où on peut les lire, et qu'une
    redirection muette serait invisible jusqu'au jour où quelqu'un présente
    sa vieille carte.
    """
    from .models import FusionPatient
    FusionPatient.all_objects.filter(absorbee=fiche).update(
        code_absorbee=fiche.code_patient,
        ancien_identifiant_absorbee=fiche.ancien_identifiant or '')
    FusionPatient.all_objects.filter(gardee=fiche).update(
        code_gardee=fiche.code_patient)


def _reporter_les_renvois(fiche):
    """Les fiches qui pointaient sur celle-ci pointent sur sa remplaçante.

    Sans cela, `PROTECT` refuserait la suppression — et la lever sans rien
    faire d'autre rendrait à ces fiches l'apparence d'un dossier ouvert.

    `update()` plutôt que `save()` : on ne veut ni signal ni trace sur des
    fiches qui n'ont pas changé de sens, seulement de relais.
    """
    from .models import Patient
    relais = fiche.remplacee_par
    Patient.all_objects.filter(fusionne_dans=fiche).update(fusionne_dans=relais)
    Patient.all_objects.filter(doublon_de=fiche).update(doublon_de=relais)
