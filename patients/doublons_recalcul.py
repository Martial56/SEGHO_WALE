"""Calculer les doublons de la base et les ranger pour qu'on puisse les lire.

Le rapprochement coûte trois minutes sur 47 800 fiches. L'écran qui les
listera ne peut donc pas le refaire à chaque affichage : on le mène à part, et
on écrit le résultat.

Deux entrées :

- `recalculer_centre` passe toute la base d'un centre. Il calcule **tout en
  mémoire**, puis remplace les paires en une seule transaction : pendant les
  trois minutes, l'écran continue de montrer le relevé précédent, entier,
  plutôt qu'une liste vide ou à moitié remplie.
- `recalculer_fiche` ne reprend que les paires d'une fiche, après son
  enregistrement.

Ce que ce module ne touche jamais : `PaireEcartee` et `ChoixFicheGardee`,
c'est-à-dire tout ce qu'une personne a décidé. Les groupes ne sont pas écrits
non plus — ils se recomposent à la lecture, ce qui évite d'avoir à les
réconcilier avec ces décisions.
"""

import threading
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q

from .doublons import (IndexBlocage, SEUIL_AVERTISSEMENT, SEUIL_BLOCAGE,
                       chercher_doublons, paire_ordonnee, scorer)

try:
    import fcntl
except ImportError:                                          # pragma: no cover
    fcntl = None


class RecalculDejaEnCours(RuntimeError):
    """Levée quand un passage complet tourne déjà."""


# ── Le verrou ───────────────────────────────────────────────────────────────
#
# Un seul recalcul complet à la fois. SQLite n'accepte qu'un écrivain : deux
# passages simultanés finiraient en « database is locked », et de toute façon
# le second referait le travail du premier.
#
# Le verrou doit être vu de tous les processus, pas du seul qui le pose : le
# passage de nuit tourne sous crontab, dans son propre processus, et gunicorn
# sert les enregistrements depuis plusieurs workers. Un `threading.Lock` ne
# protégeait que l'un d'eux.
#
# `flock` sur un fichier plutôt qu'une ligne en base : il se relâche tout seul
# quand le processus meurt, même tué net. Une ligne en base resterait posée
# après un arrêt brutal, et il faudrait inventer une péremption pour la
# lever — avec le risque de lever celle d'un recalcul encore en cours.
#
# Deux niveaux, qui donnent exactement le comportement voulu :
#   • le passage complet prend un verrou **exclusif** ;
#   • le recalcul ciblé prend un verrou **partagé** — plusieurs peuvent donc
#     tourner ensemble, mais aucun pendant un passage complet, et aucun
#     passage complet ne peut démarrer pendant qu'un ciblé écrit.

#: Le fichier n'est qu'un support : rien n'y est écrit, seul son verrou compte.
VERROU_DEFAUT = '.verrou-doublons'


def chemin_verrou():
    defaut = Path(settings.BASE_DIR) / VERROU_DEFAUT
    return Path(getattr(settings, 'DOUBLONS_PATIENTS_VERROU', defaut))


#: Repli quand `fcntl` manque (Windows). Le cloisonnement entre processus est
#: alors perdu : on le dit plutôt que de le laisser croire.
_verrou_processus = threading.Lock()


@contextmanager
def verrou(exclusif):
    """Prend le verrou, ou lève `RecalculDejaEnCours` s'il est déjà pris."""
    if fcntl is None:                                        # pragma: no cover
        if not _verrou_processus.acquire(blocking=False):
            raise RecalculDejaEnCours('Un recalcul tourne déjà.')
        try:
            yield
        finally:
            _verrou_processus.release()
        return

    chemin = chemin_verrou()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fichier = open(chemin, 'a+')
    mode = (fcntl.LOCK_EX if exclusif else fcntl.LOCK_SH) | fcntl.LOCK_NB
    try:
        try:
            fcntl.flock(fichier.fileno(), mode)
        except OSError:
            raise RecalculDejaEnCours(
                'Un recalcul complet tourne déjà : celui-ci est inutile.')
        yield
    finally:
        # Fermer relâche le verrou : il est attaché à cette ouverture-ci.
        fichier.close()


def recalcul_complet_en_cours():
    """Vrai tant qu'un passage complet tourne, ici ou dans un autre processus.

    Testé en demandant le verrou partagé : il n'est refusé que par un verrou
    exclusif, c'est-à-dire par un passage complet.
    """
    try:
        with verrou(exclusif=False):
            return False
    except RecalculDejaEnCours:
        return True


def _fiches_du_centre(centre_id):
    from .models import Patient
    return (Patient.all_objects
            .filter(centre_id=centre_id, fusionne_dans__isnull=True, masque=False)
            .only('pk', 'nom', 'prenoms', 'date_naissance', 'date_naissance_approx',
                  'telephone', 'telephone2', 'sexe', 'centre_id'))


def _ecartees(centre_id):
    from .models import PaireEcartee
    return set(PaireEcartee.all_objects.filter(centre_id=centre_id)
               .values_list('patient_a_id', 'patient_b_id'))


def _niveau(score):
    return 'certain' if score >= SEUIL_BLOCAGE else 'avertissement'


def calculer_paires(centre_id, avancement=None):
    """Les paires d'un centre, en mémoire, sans rien écrire.

    Rendu : {(pk_a, pk_b): (score, details)}, `pk_a < pk_b`.
    """
    fiches = list(_fiches_du_centre(centre_id))
    total = len(fiches)
    if avancement:
        avancement.etape('Indexation des fiches…', total=total)

    index = IndexBlocage()
    for fiche in fiches:
        index.ajouter(fiche.pk, fiche)

    if avancement:
        avancement.etape('Rapprochement…', total=total)

    ecartees = _ecartees(centre_id)
    paires = {}
    for fiche in fiches:
        for autre_pk, autre in index.candidats(fiche):
            if autre_pk == fiche.pk:
                continue
            cle = paire_ordonnee(fiche.pk, autre_pk)
            if cle in paires or cle in ecartees:
                continue
            correspondance = scorer(fiche, autre)
            if correspondance.score >= SEUIL_AVERTISSEMENT:
                paires[cle] = (correspondance.score, correspondance.details)
        if avancement:
            avancement.ajouter(traites=1)
    return paires


@transaction.atomic
def _remplacer(centre_id, paires):
    """Supprime l'ancien relevé et écrit le nouveau, d'un seul coup.

    Hors transaction, l'écran afficherait une liste vide le temps de
    l'écriture — soit, sur un centre entier, plusieurs secondes.
    """
    from .models import DoublonPaire

    DoublonPaire.all_objects.filter(centre_id=centre_id).delete()
    DoublonPaire.all_objects.bulk_create(
        [DoublonPaire(centre_id=centre_id, patient_a_id=a, patient_b_id=b,
                      score=score, niveau=_niveau(score), details=details)
         for (a, b), (score, details) in paires.items()],
        batch_size=2000)
    return len(paires)


def recalculer_centre(centre_id, avancement=None):
    """Le passage complet d'un centre. Rend le nombre de paires écrites."""
    with verrou(exclusif=True):
        completer_cles_manquantes(centre_id, avancement)
        paires = calculer_paires(centre_id, avancement)
        if avancement:
            avancement.etape('Écriture…')
        return _remplacer(centre_id, paires)


def completer_cles_manquantes(centre_id, avancement=None):
    """Réécrit les clés phonétiques des fiches qui n'en ont aucune.

    La migration qui remplit la table passe sans rien écrire si le module des
    clés a disparu ; et une fiche créée par un chemin qui ne passe ni par
    `save()` ni par l'import n'en aurait pas non plus. Sans ce rattrapage, il
    faudrait s'en apercevoir et lancer `--cles` à la main — autant dire que la
    ressemblance sonore serait muette sans que personne le sache.

    Une fiche peut légitimement n'avoir aucune clé : « KA YA » n'a pas un mot
    d'au moins trois lettres. On ne réécrit donc que celles qui devraient en
    porter une.
    """
    from .cles_phonetiques import cles, rafraichir
    from .models import Patient

    sans_cle = (Patient.all_objects
                .filter(centre_id=centre_id, cles_phonetiques__isnull=True)
                .only('pk', 'nom', 'prenoms', 'date_naissance', 'centre_id'))

    lot, ecrites = [], 0
    for fiche in sans_cle.iterator(chunk_size=2000):
        if not cles(fiche.nom, fiche.prenoms):
            continue                       # rien à en tirer, c'est normal
        lot.append(fiche)
        if len(lot) >= 2000:
            ecrites += rafraichir(lot)
            lot = []
    if lot:
        ecrites += rafraichir(lot)
    if ecrites and avancement:
        avancement.etape(f'{ecrites} clé(s) phonétique(s) rattrapée(s)…')
    return ecrites


def recalculer_fiche(patient):
    """Reprend les seules paires d'une fiche.

    Ignoré pendant un passage complet : celui-ci couvre déjà cette fiche, et
    sur SQLite deux écrivains à la fois donnent « database is locked ».
    """
    try:
        with verrou(exclusif=False):
            return _recalculer_fiche(patient)
    except RecalculDejaEnCours:
        # Un passage complet tourne : il couvre déjà cette fiche, et sur
        # SQLite deux écrivains à la fois donnent « database is locked ».
        return 0


def _recalculer_fiche(patient):
    from .models import DoublonPaire

    if patient.fusionne_dans_id or patient.masque:
        DoublonPaire.all_objects.filter(
            Q(patient_a=patient) | Q(patient_b=patient)).delete()
        return 0

    perimetre = _fiches_du_centre(patient.centre_id).exclude(pk=patient.pk)
    # `limite=None` : l'écran de saisie n'en montre que cinq, le relevé les
    # veut toutes.
    correspondances = chercher_doublons(
        patient, exclure_pk=patient.pk, queryset=perimetre, limite=None)

    lignes = []
    for c in correspondances:
        a, b = paire_ordonnee(patient.pk, c.patient.pk)
        lignes.append(DoublonPaire(
            centre_id=patient.centre_id, patient_a_id=a, patient_b_id=b,
            score=c.score, niveau=_niveau(c.score), details=c.details))

    with transaction.atomic():
        DoublonPaire.all_objects.filter(
            Q(patient_a=patient) | Q(patient_b=patient)).delete()
        if lignes:
            DoublonPaire.all_objects.bulk_create(lignes, ignore_conflicts=True)
    return len(lignes)


def planifier(patient_pk, centre):
    """Reprend le relevé de cette fiche, une fois l'enregistrement acquis.

    `on_commit` plutôt qu'un fil lancé tout de suite : le fil ouvre sa propre
    connexion, et une fiche encore dans la transaction de la requête lui serait
    invisible. En écriture immédiate — le cas courant — la fonction part sans
    attendre.

    Le fil n'hérite pas du contexte de la requête : le centre lui est passé et
    réinstallé, comme dans `core.taches`. Sa connexion est refermée à la fin —
    sur SQLite elle garderait sinon le fichier verrouillé.

    Si le worker est recyclé pendant le fil, ce recalcul-là est perdu ; le
    passage de nuit le répare.
    """
    def demarrer():
        threading.Thread(target=_recalculer_en_fond, args=(patient_pk, centre),
                         name=f'doublons-{patient_pk}', daemon=True).start()

    transaction.on_commit(demarrer)


def _recalculer_en_fond(patient_pk, centre):
    from core.middleware import centre_actif
    from .models import Patient
    try:
        with centre_actif(centre):
            patient = Patient.all_objects.filter(pk=patient_pk).first()
            if patient is not None:
                recalculer_fiche(patient)
    except Exception:
        # Un doublon non relevé n'est pas une raison de faire tomber la
        # requête qui vient de réussir. Le passage de nuit rattrapera.
        pass
    finally:
        connection.close()
