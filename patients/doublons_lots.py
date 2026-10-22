"""Traiter plusieurs groupes d'un coup, sans jamais relâcher les contrôles.

Un lot n'est pas une boucle sur l'action unitaire. Trois choses l'en séparent :

* **Ce qui est confirmé est ce qui est exécuté.** La liste des groupes est
  figée au moment de la confirmation (`LotDoublons.cles`). Entre l'écran et le
  clic, quelqu'un a pu fusionner une de ces fiches depuis un autre poste : le
  groupe passe alors dans les écartés avec sa raison, il n'est ni traité en
  silence ni cause d'un échec général.
* **L'éligibilité se juge groupe par groupe, et se dit.** Un groupe dont une
  fiche porte des factures n'est pas masquable ; un groupe dont les deux
  fiches se contredisent sur un champ n'est pas fusionnable sans choix. Ces
  groupes sont ignorés **et listés** : on ne les traite pas à l'aveugle, on
  dit lesquels restent à faire à la main.
* **Les « à vérifier » ne se masquent ni ne se fusionnent en lot.** Un
  prénom voisin et deux dates qui ne concordent pas, ce sont souvent deux
  sœurs ; les traiter cent à la fois reviendrait à faire disparaître des
  dossiers vivants sans que personne les ait regardés. Ces groupes passent
  dans les ignorés, et la seule action de lot qui leur reste est « pas un
  doublon ». À l'unité, l'écran de comparaison permet toujours tout.
* **Le relevé se reprend une fois, à la fin.** `recalculer_fiche` coûte deux
  dixièmes de seconde ; appelé après chacun des neuf cents masquages, il
  ferait trois minutes. Les paires des fiches traitées sont supprimées d'un
  coup, et le passage de nuit refera le reste.

Tout le reste est celui de l'unité : la permission, le centre actif, le
verrou partagé, et la revérification au moment d'agir.
"""

from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from .doublons import paire_ordonnee
from .doublons_groupes import fiche_a_garder, membres_depuis_cle
from .liens_patient import champs_en_plus, comptes_par_table, oublier_les_totaux
from .models import LotDoublons, PaireEcartee, Patient


#: La raison inscrite au bilan quand un groupe « à vérifier » a été
#: sélectionné pour un masquage ou une fusion.
A_VERIFIER = 'à vérifier : à traiter un par un'


class LotRefuse(Exception):
    """Ce qui empêche le lot entier, en une phrase lisible."""


@dataclass
class Prevu:
    """Un groupe retenu, et ce qu'on va lui faire — montré avant d'agir."""
    cle: str
    gardee: Patient
    visee: Patient                       # masquée, ou versée dans la gardée
    membres: list = field(default_factory=list)


# ── Qui est touché, et pourquoi ─────────────────────────────────────────────

def _couple(fiches, par_table):
    """(gardée, l'autre) d'un groupe de deux, selon le choix humain ou la
    suggestion. None si le groupe n'a pas exactement deux fiches."""
    if len(fiches) != 2:
        return None, None
    garder, _choisis = fiche_a_garder(fiches, par_table)
    gardee = next((f for f in fiches if f.pk == garder), None)
    autre = next((f for f in fiches if f.pk != garder), None)
    return gardee, autre


def _charger(cles, perimetre):
    """{clé: [fiches]} — les fiches de chaque groupe, dans le centre actif."""
    toutes = {pk for cle in cles for pk in membres_depuis_cle(cle)}
    fiches = {f.pk: f for f in perimetre.filter(pk__in=toutes)
              .select_related('assurance')}
    return {cle: [fiches[pk] for pk in membres_depuis_cle(cle) if pk in fiches]
            for cle in cles}


def niveaux(cles, centre_id=None):
    """{clé: 'certain' | 'avertissement'} — le niveau de chaque groupe.

    Lu sur les paires et non sur l'index : l'index est en cache, et c'est de
    cette lecture-ci que dépend l'autorisation de masquer. Un groupe est
    quasi certain dès qu'un de ses liens l'est — c'est la règle de l'index et
    celle de la pastille affichée.

    Un groupe dont plus aucune paire ne subsiste est tenu pour « à vérifier » :
    devant un relevé qu'on ne sait plus lire, on refuse plutôt qu'on agit.

    Avec le centre, on prend **toutes** ses paires certaines d'un coup : mille
    lignes, quelques millisecondes. Les désigner par leurs fiches — dix-sept
    mille identifiants des deux côtés du `IN` — demandait vingt-huit secondes
    sur le relevé entier, et « tout sélectionner » est précisément le cas où
    la règle doit tenir.
    """
    from .models import DoublonPaire

    lignes = DoublonPaire.all_objects.filter(niveau='certain')
    if centre_id is not None:
        lignes = lignes.filter(centre_id=centre_id)
    else:
        pks = {pk for cle in cles for pk in membres_depuis_cle(cle)}
        lignes = lignes.filter(patient_a_id__in=pks, patient_b_id__in=pks)
    certaines = set(lignes.values_list('patient_a_id', 'patient_b_id'))
    reponse = {}
    for cle in cles:
        membres = membres_depuis_cle(cle)
        sur = any(paire_ordonnee(x, y) in certaines
                  for i, x in enumerate(membres) for y in membres[i + 1:])
        reponse[cle] = 'certain' if sur else 'avertissement'
    return reponse


def examiner(action, cles, perimetre):
    """(prévus, ignorés) pour cette action — l'écran de confirmation lit ça.

    `ignorés` est une liste de (clé, raison en clair) : « lesquels » et
    « pourquoi », parce qu'un groupe écarté sans explication se lit comme une
    panne.
    """
    groupes = _charger(cles, perimetre)
    # Une seule lecture des données rattachées pour tout le lot : une par
    # groupe ferait treize requêtes fois neuf cents.
    par_table = comptes_par_table([f.pk for g in groupes.values() for f in g])
    # Une seule lecture des paires, elle aussi : le niveau décide de ce que
    # le lot a le droit de faire.
    centres = {f.centre_id for g in groupes.values() for f in g}
    par_niveau = (niveaux(cles, centres.pop() if len(centres) == 1 else None)
                  if action in ('masquer', 'fusionner') else {})

    prevus, ignores = [], []
    for cle in cles:
        fiches = groupes.get(cle) or []
        for fiche in fiches:
            fiche.rattache_total = sum(par_table.get(fiche.pk, {}).values())
        refus = _refus(action, fiches, par_table,
                       par_niveau.get(cle, 'certain'))
        if refus:
            ignores.append((cle, refus))
            continue
        gardee, visee = _couple(fiches, par_table)
        prevus.append(Prevu(cle=cle, gardee=gardee, visee=visee, membres=fiches))
    return prevus, ignores


def _refus(action, fiches, par_table, niveau='certain'):
    """La raison de ne pas traiter ce groupe, ou '' s'il est éligible."""
    if len(fiches) < 2:
        return "Ce groupe n'existe plus."
    if len(fiches) != 2:
        return 'Plus de deux fiches : à traiter une par une.'
    if any(f.masque or f.fusionne_dans_id for f in fiches):
        return 'Une de ces fiches a déjà été traitée.'
    if niveau != 'certain' and action in ('masquer', 'fusionner'):
        return A_VERIFIER
    if action == 'masquer':
        return _refus_de_masquer(fiches, par_table)
    if action == 'fusionner':
        return _refus_de_fusionner(fiches, par_table)
    return ''


def _refus_de_masquer(fiches, par_table):
    """Masquer retire une fiche sans rien déplacer : elle doit ne rien porter.

    Ni données rattachées, ni champ que l'autre n'aurait pas — une allergie
    perdue ne ferait pas de bruit.
    """
    gardee, autre = _couple(fiches, par_table)
    if autre is None:
        return 'Impossible de désigner la fiche à retirer.'
    if sum(par_table.get(autre.pk, {}).values()):
        return f'{autre.code_patient} porte des données : il faut la fusionner.'
    en_plus = champs_en_plus(autre, gardee)
    if en_plus:
        return (f'{autre.code_patient} porte des informations que '
                f"{gardee.code_patient} n'a pas : " + ', '.join(en_plus) + '.')
    return ''


def _refus_de_fusionner(fiches, par_table):
    """Fusionner en lot n'est permis que là où il n'y a rien à choisir.

    `obstacles()` interroge la base pour chaque paire — hospitalisation
    ouverte, décès, rendez-vous en double. C'est irréductible : ces
    questions-là se posent fiche par fiche.
    """
    from .fusion import obstacles, propositions

    gardee, absorbee = _couple(fiches, par_table)
    if gardee is None or absorbee is None:
        return 'Impossible de désigner la fiche à garder.'
    empechements = obstacles(gardee, absorbee)
    if empechements:
        # Refus comme avertissements : dans les deux cas, quelqu'un doit
        # regarder. Le lot ne tranche pas à la place d'une personne.
        return empechements[0].message
    conflits = [p.libelle for p in propositions(gardee, absorbee) if p.obligatoire]
    if conflits:
        return 'Champs à choisir : ' + ', '.join(conflits) + '.'
    return ''


# ── Préparer, puis exécuter ─────────────────────────────────────────────────

def preparer(action, cles, utilisateur, centre, raison=''):
    """Fige la liste et rend le lot, non encore exécuté."""
    if action not in dict(LotDoublons.ACTIONS):
        raise LotRefuse('Action inconnue.')
    return LotDoublons.all_objects.create(
        centre=centre, action=action, raison=raison or '',
        utilisateur=utilisateur if utilisateur
        and utilisateur.is_authenticated else None,
        cles=list(cles))


def executer(lot, perimetre, utilisateur, avancement=None):
    """Applique le lot à la liste figée. Rend le lot, mis à jour."""
    from .doublons_recalcul import RecalculDejaEnCours, verrou

    if lot.etat != 'prepare':
        raise LotRefuse('Ce lot a déjà été exécuté.')
    try:
        with verrou(exclusif=False):
            return _executer(lot, perimetre, utilisateur, avancement)
    except RecalculDejaEnCours:
        raise LotRefuse('Un recalcul complet des doublons est en cours : '
                        'réessayez dans un moment.')


def _executer(lot, perimetre, utilisateur, avancement):
    faire = {'masquer': _masquer_un, 'ecarter': _ecarter_un,
             'fusionner': _fusionner_un}[lot.action]

    prevus, ignores = examiner(lot.action, lot.cles, perimetre)
    if avancement is not None:
        # L'étape est posée une fois : `etape()` écrit en base à chaque
        # appel, et deux cent vingt écritures pour une jauge coûteraient plus
        # que le travail. `ajouter()`, lui, s'écrit par paliers.
        avancement.etape('Traitement…', total=len(prevus))
    # `ignores` vient de l'examen, `ecartes` de l'exécution : deux listes
    # disjointes, sinon le bilan compterait deux fois les mêmes groupes.
    faits, ecartes = [], []
    touchees = []
    for prevu in prevus:
        if avancement is not None:
            avancement.ajouter(traites=1)
        try:
            with transaction.atomic():
                fait = faire(lot, prevu, utilisateur)
        except Exception as erreur:                       # noqa: BLE001
            # Un groupe qui résiste n'emporte pas les autres : il est dit.
            ecartes.append((prevu.cle, str(erreur) or type(erreur).__name__))
            continue
        faits.append(fait)
        touchees.extend([prevu.gardee.pk, prevu.visee.pk])

    _oublier_le_releve(touchees)
    lot.faits = faits
    lot.ignores = [list(i) for i in ignores]
    lot.ecartes = [list(e) for e in ecartes]
    lot.etat = 'execute'
    lot.execute_le = timezone.now()
    lot.save(update_fields=['faits', 'ignores', 'ecartes', 'etat', 'execute_le'])
    return lot


def _masquer_un(lot, prevu, utilisateur):
    fiche, gardee = prevu.visee, prevu.gardee
    fiche.masque = True
    fiche.doublon_de = gardee
    fiche.masque_par = utilisateur if utilisateur and utilisateur.is_authenticated else None
    fiche.masque_le = timezone.now()
    fiche.save(update_fields=['masque', 'doublon_de', 'masque_par', 'masque_le'])
    return {'cle': prevu.cle, 'masquee': fiche.pk, 'gardee': gardee.pk,
            'code': fiche.code_patient}


def _ecarter_un(lot, prevu, utilisateur):
    a, b = paire_ordonnee(prevu.gardee.pk, prevu.visee.pk)
    PaireEcartee.all_objects.update_or_create(
        patient_a_id=a, patient_b_id=b,
        defaults={'utilisateur': utilisateur, 'raison': lot.raison,
                  'centre_id': prevu.gardee.centre_id})
    return {'cle': prevu.cle, 'a': a, 'b': b}


def _fusionner_un(lot, prevu, utilisateur):
    from .fusion import Choix, _fusionner

    # `_fusionner` et non `fusionner` : le verrou partagé est déjà pris par
    # le lot, le reprendre à chaque fusion ne servirait qu'à ralentir.
    fusion = _fusionner(prevu.gardee, prevu.visee, Choix(), utilisateur)
    return {'cle': prevu.cle, 'fusion': fusion.pk,
            'code': prevu.visee.code_patient}


def _oublier_le_releve(pks):
    """Les paires des fiches traitées partent d'un coup.

    Une par une, `recalculer_fiche` coûterait deux dixièmes de seconde par
    fiche — trois minutes pour neuf cents groupes. Ce qu'on perd ici, c'est
    le relevé des fiches **gardées**, que le passage de nuit refera.
    """
    from django.db.models import Q
    from .models import DoublonPaire

    if not pks:
        return
    DoublonPaire.all_objects.filter(
        Q(patient_a_id__in=pks) | Q(patient_b_id__in=pks)).delete()
    oublier_les_totaux()


# ── Défaire un lot ──────────────────────────────────────────────────────────

def annuler(lot, perimetre, utilisateur):
    """Défait ce qui peut l'être, et dit ce qui ne le peut plus."""
    if lot.etat != 'execute':
        raise LotRefuse("Ce lot n'a pas été exécuté.")

    defaire = {'masquer': _defaire_masquage, 'ecarter': _defaire_ecartement,
               'fusionner': _defaire_fusion}[lot.action]
    restants = []
    touchees = []
    # Les fusions se défont de la plus récente à la plus ancienne : une
    # chaîne faite dans l'ordre se défait dans l'ordre inverse.
    for fait in reversed(lot.faits):
        try:
            with transaction.atomic():
                touchees.extend(defaire(fait, perimetre, utilisateur))
        except Exception as erreur:                       # noqa: BLE001
            restants.append([fait.get('cle', ''), str(erreur)
                             or type(erreur).__name__])

    _oublier_le_releve(touchees)
    lot.etat = 'annule'
    lot.annule_le = timezone.now()
    lot.annule_par = (utilisateur if utilisateur
                      and utilisateur.is_authenticated else None)
    lot.annulation_partielle = restants
    lot.save(update_fields=['etat', 'annule_le', 'annule_par',
                            'annulation_partielle'])
    return restants


def _defaire_masquage(fait, perimetre, utilisateur):
    fiche = perimetre.filter(pk=fait.get('masquee'), masque=True).first()
    if fiche is None:
        raise LotRefuse('Cette fiche a déjà été réaffichée ou supprimée.')
    fiche.masque = False
    fiche.doublon_de = None
    fiche.masque_par = None
    fiche.masque_le = None
    fiche.save(update_fields=['masque', 'doublon_de', 'masque_par', 'masque_le'])
    return [fiche.pk]


def _defaire_ecartement(fait, perimetre, utilisateur):
    supprimees, _ = PaireEcartee.all_objects.filter(
        patient_a_id=fait.get('a'), patient_b_id=fait.get('b')).delete()
    if not supprimees:
        raise LotRefuse('Cette paire a déjà été reprise.')
    return [fait.get('a'), fait.get('b')]


def _defaire_fusion(fait, perimetre, utilisateur):
    from .fusion import FusionRefusee, annuler as annuler_fusion
    from .models import FusionPatient

    fusion = FusionPatient.all_objects.filter(pk=fait.get('fusion')).first()
    if fusion is None:
        raise LotRefuse('Cette fusion a disparu du journal.')
    if not fusion.active:
        raise LotRefuse('Cette fusion a déjà été annulée.')
    try:
        annuler_fusion(fusion, utilisateur)
    except FusionRefusee as refus:
        raise LotRefuse(str(refus))
    return [fusion.gardee_id, fusion.absorbee_id]
