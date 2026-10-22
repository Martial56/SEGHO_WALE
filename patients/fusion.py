"""Fusionner deux fiches patient, et pouvoir le défaire.

On ne copie rien et on ne supprime rien : on **change le propriétaire** des
lignes liées (`UPDATE patient_id`), dans une seule transaction, après avoir
compté ce qu'il y avait de chaque côté et avant d'avoir vérifié qu'on le
retrouve. Si un chiffre ne tombe pas juste, la transaction retombe et rien n'a
eu lieu.

Les déplacements passent par `queryset.update()`, jamais par `save()` : aucun
signal ne se redéclenche — rien n'est ré-ancré côté blockchain —, et
`date_modification` ne bouge pas sur des lignes qu'on n'a pas modifiées.

La liste des tables vient de `liens_patient.liens()`, c'est-à-dire de
l'introspection : un module ajouté demain sera déplacé sans qu'on y pense.
Trois chemins lui échappent, et sont traités à part ici :

- `LogActivite`, qui vise n'importe quel objet par un lien générique ;
- les quatre registres (CPN, accouchement, postnatale, curatif), qui pendent
  d'un rendez-vous et suivent donc le leur, sans qu'on y touche ;
- `PaireEcartee`, qui n'appartient pas à la fiche mais la désigne : les
  décisions « pas un doublon » de la fiche absorbée sont **reportées** sur la
  fiche gardée, pas déplacées.

Une fusion absorbe **une** fiche. Un groupe de trois se traite en deux fois.

Les deux seules sauvegardes de la fusion — la fiche gardée qui reçoit les
champs retenus, la fiche absorbée qui reçoit son `fusionne_dans` — se font
sans le journal automatique (`_skip_auto_log`). Sans cela, le signal
`post_save` écrirait une trace *pendant* la fusion : sur la fiche gardée
après le comptage d'avant, ce qui faisait refuser à tort une fusion où un
champ changeait ; sur la fiche absorbée après la vérification, ce qui lui
laissait de l'historique alors qu'elle n'est plus consultable. Une trace
unique et précise est écrite à la place, une fois les comptes vérifiés.
"""

from dataclasses import dataclass, field as champ_defaut
from datetime import date as type_date, datetime

from django.apps import apps
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from .doublons import paire_ordonnee
from .doublons_groupes import valeur_affichee
from .doublons_recalcul import RecalculDejaEnCours, planifier, verrou
from .liens_patient import comptes_par_table, liens


class FusionRefusee(RuntimeError):
    """La fusion ne peut pas avoir lieu, et on dit pourquoi."""


class FusionIncoherente(RuntimeError):
    """Les comptes ne tombent pas juste : la transaction doit retomber."""


#: Repères techniques des deux traces que la fusion écrit elle-même. Un écran
#: qui veut les retrouver s'appuie sur le code, jamais sur le texte.
CODE_FUSION = 'patient.fusion'
CODE_ANNULATION = 'patient.fusion.annulee'


# ── Les champs de la fiche ──────────────────────────────────────────────────

#: Ce qui ne se choisit pas : l'identité de la ligne, les horodatages, et les
#: marques du mécanisme des doublons.
CHAMPS_HORS_CHOIX = {
    'id', 'code_patient', 'centre', 'date_creation', 'date_modification',
    'masque', 'fusionne_dans', 'doublon_de',
    # Qui a masqué, et quand : la décision porte sur une fiche précise, elle
    # ne se recopie pas sur une autre.
    'masque_par', 'masque_le',
    # Voyage avec `date_naissance` et ne se choisit pas seule : prendre la date
    # de l'autre fiche sans sa case « approximative » transformerait une
    # estimation en date certaine.
    'date_naissance_approx',
}

#: Additionnés plutôt que choisis : perdre une allergie serait silencieux.
CHAMPS_ADDITIONNES = ('allergies', 'antecedents')

#: Jamais de valeur par défaut quand les deux fiches se contredisent : c'est à
#: une personne de trancher, et le logiciel ne suppose pas.
CHAMPS_SANS_DEFAUT = ('sexe',)

#: Une hospitalisation « en cours » occupe un lit. Un brouillon, non.
HOSPITALISATION_ACTIVE = ('confirme', 'hospitalise')

#: Les quatre registres pendent du rendez-vous ; ils interdisent de l'annuler.
REGISTRES_RDV = ('registre_cpn', 'registre_accouchement',
                 'registre_postnatale', 'registre_curatif')


def champs_fusionnables():
    from .models import Patient
    return [f for f in Patient._meta.concrete_fields
            if f.name not in CHAMPS_HORS_CHOIX]


def _lire(fiche, champ):
    """La valeur brute : un identifiant pour une relation, un chemin pour un
    fichier. `attname` donne `assurance_id` là où `name` donnerait l'objet."""
    valeur = getattr(fiche, champ.attname, None)
    if hasattr(valeur, 'storage'):                       # FieldFile
        return valeur.name or ''
    return valeur


def _rempli(valeur):
    if valeur is None or valeur is False:
        return False
    if isinstance(valeur, str):
        return bool(valeur.strip())
    return True


def additionner(a, b):
    """Les deux textes, sans répéter ce qui est déjà dit.

    Ligne à ligne : « Pénicilline » écrit des deux côtés ne compte qu'une
    fois, mais « Pénicilline » et « Arachide » se retrouvent tous les deux.
    """
    morceaux, vus = [], set()
    for texte in (a, b):
        for ligne in str(texte or '').splitlines():
            ligne = ligne.strip()
            if ligne and ligne.casefold() not in vus:
                vus.add(ligne.casefold())
                morceaux.append(ligne)
    return '\n'.join(morceaux)


@dataclass
class Proposition:
    """Un champ, ce qu'en dit chaque fiche, et ce qu'on propose de retenir."""
    champ: str
    libelle: str
    vue_gardee: str
    vue_absorbee: str
    identique: bool
    defaut: str                  # 'gardee' | 'absorbee' | 'additionner' | ''
    obligatoire: bool
    motif: str
    texte: str                   # la valeur proposée, modifiable à la main


def propositions(gardee, absorbee):
    """Champ par champ : les deux valeurs, le défaut proposé, et pourquoi."""
    lignes = []
    for f in champs_fusionnables():
        a, b = _lire(gardee, f), _lire(absorbee, f)
        vue_a = valeur_affichee(gardee, f.name)
        vue_b = valeur_affichee(absorbee, f.name)
        identique = a == b
        obligatoire, motif = False, ''
        if identique:
            defaut, texte = 'gardee', vue_a
        elif not _rempli(a) and _rempli(b):
            defaut, texte = 'absorbee', vue_b
            motif = 'la fiche gardée est vide'
        elif _rempli(a) and not _rempli(b):
            defaut, texte = 'gardee', vue_a
        elif f.name in CHAMPS_ADDITIONNES:
            defaut, texte = 'additionner', additionner(a, b)
            motif = 'les deux textes sont conservés'
        elif f.name in CHAMPS_SANS_DEFAUT:
            defaut, texte = '', ''
            obligatoire = True
            motif = 'les deux fiches se contredisent'
        else:
            defaut, texte = 'gardee', vue_a
        lignes.append(Proposition(
            champ=f.name, libelle=str(f.verbose_name).capitalize(),
            vue_gardee=vue_a, vue_absorbee=vue_b, identique=identique,
            defaut=defaut, obligatoire=obligatoire, motif=motif, texte=texte))
    return lignes


# ── Ce qui bloque, ce qui demande à choisir, ce qui se signale ──────────────

@dataclass
class Obstacle:
    code: str
    gravite: str                 # 'refus' | 'choix' | 'confirmation' | 'signal'
    message: str
    details: dict = champ_defaut(default_factory=dict)


def _rdv_rattache(rdv):
    """Ce qui interdit d'annuler ce rendez-vous. Vide s'il est annulable."""
    if getattr(rdv, 'consultation', None) is not None:
        return 'une consultation y est rattachée'
    for nom in REGISTRES_RDV:
        if getattr(rdv, nom, None) is not None:
            return 'un registre y est rattaché'
    return ''


def rdv_en_double(gardee, absorbee):
    """Les rendez-vous le même jour avec le même médecin, de part et d'autre.

    Seul celui de la fiche absorbée peut être annulé : c'est lui le second,
    créé par la seconde saisie. Et seulement s'il ne porte rien.
    """
    from .models import RendezVous

    def par_jour(fiche):
        index = {}
        lignes = (RendezVous.all_objects
                  .filter(patient=fiche, medecin__isnull=False)
                  .exclude(statut='annule')
                  .select_related('medecin'))
        for rdv in lignes:
            index.setdefault((rdv.date_heure.date(), rdv.medecin_id), []).append(rdv)
        return index

    cote_gardee, cote_absorbee = par_jour(gardee), par_jour(absorbee)
    doubles = []
    for cle, ceux_de_la_gardee in cote_gardee.items():
        for rdv in cote_absorbee.get(cle, []):
            empeche = _rdv_rattache(rdv)
            doubles.append({'gardee': ceux_de_la_gardee[0], 'absorbee': rdv,
                            'annulable': not empeche, 'empeche': empeche})
    return doubles


def hospitalisations_actives(gardee, absorbee):
    from hospitalisation.models import Hospitalisation
    return list(Hospitalisation.all_objects
                .filter(patient__in=[gardee, absorbee],
                        statut__in=HOSPITALISATION_ACTIVE)
                .select_related('patient', 'chambre'))


def obstacles(gardee, absorbee):
    """Tout ce que l'écran doit dire avant qu'on valide."""
    from hospitalisation.models import RegistreDeces

    trouves = []
    if gardee.centre_id != absorbee.centre_id:
        trouves.append(Obstacle(
            'centres', 'refus',
            'Ces deux fiches appartiennent à des centres différents.'))

    deces = list(RegistreDeces.all_objects.filter(patient__in=[gardee, absorbee]))
    if deces:
        trouves.append(Obstacle(
            'deces', 'confirmation',
            "Un décès est enregistré sur l'une de ces fiches : la fiche gardée "
            "sera celle d'une personne décédée.",
            {'codes': [d.code for d in deces]}))

    hospitalisations = hospitalisations_actives(gardee, absorbee)
    if len({h.patient_id for h in hospitalisations}) == 2:
        trouves.append(Obstacle(
            'hospitalisations', 'choix',
            "Les deux fiches ont une hospitalisation en cours : choisissez "
            "celle qui reste active. L'autre sera clôturée « annulée (doublon) » "
            "et son lit libéré.",
            {'hospitalisations': hospitalisations}))

    if any(p.obligatoire for p in propositions(gardee, absorbee)):
        trouves.append(Obstacle(
            'sexe', 'choix',
            "Les deux fiches ne donnent pas le même sexe : choisissez, "
            "il n'y a pas de valeur par défaut."))

    doubles = rdv_en_double(gardee, absorbee)
    if doubles:
        trouves.append(Obstacle(
            'rdv', 'signal',
            f"{len(doubles)} rendez-vous le même jour avec le même médecin.",
            {'paires': doubles}))
    return trouves


def apercu(gardee, absorbee):
    """« 3 rendez-vous et 1 facture » — ce que la fusion va déplacer."""
    from .liens_patient import libelle

    par_table = comptes_par_table([absorbee.pk]).get(absorbee.pk, {})
    modeles = {(m._meta.app_label, m.__name__): m for m, _c, _l in liens()}
    morceaux = [f'{nombre} {libelle(cle, modeles[cle], nombre).lower()}'
                for cle, nombre in sorted(par_table.items())]
    return {'total': sum(par_table.values()), 'morceaux': morceaux,
            'par_table': par_table}


# ── Les choix d'une personne ────────────────────────────────────────────────

@dataclass
class Choix:
    """Ce que l'écran a recueilli avant de valider.

    `champs` : {nom du champ: ('gardee'|'absorbee'|'manuel', texte saisi)}.
    """
    champs: dict = champ_defaut(default_factory=dict)
    hospitalisation_active: int = None
    rdv_a_annuler: list = champ_defaut(default_factory=list)
    deces_confirme: bool = False


# ── Faire la fusion ─────────────────────────────────────────────────────────

def fusionner(gardee, absorbee, choix, utilisateur=None):
    """Fusionne, ou lève. Rend la `FusionPatient` écrite.

    Le verrou partagé, comme le recalcul ciblé : jamais de fusion pendant un
    passage complet, qui réécrirait le relevé par-dessus. Plusieurs fusions
    peuvent en revanche se suivre sans se gêner.
    """
    try:
        with verrou(exclusif=False):
            return _fusionner(gardee, absorbee, choix, utilisateur)
    except RecalculDejaEnCours:
        raise FusionRefusee(
            'Un recalcul complet des doublons est en cours : réessayez dans '
            'un moment.')


@transaction.atomic
def _fusionner(gardee, absorbee, choix, utilisateur):
    from .models import FusionPatient

    _verifier(gardee, absorbee, choix)

    # Relevés **avant** tout déplacement : une fois les rendez-vous passés à la
    # fiche gardée, on ne saurait plus lesquels venaient de l'autre.
    doubles = rdv_en_double(gardee, absorbee)
    actives = hospitalisations_actives(gardee, absorbee)
    avant_gardee = comptes_par_table([gardee.pk])[gardee.pk]
    avant_absorbee = comptes_par_table([absorbee.pk])[absorbee.pk]
    avant_journal = _compter_traces(gardee.pk), _compter_traces(absorbee.pk)

    copie = {f.name: _en_json(f, _lire(absorbee, f))
             for f in absorbee._meta.concrete_fields}
    champs = _appliquer_les_champs(gardee, absorbee, choix)

    lignes = _deplacer(gardee, absorbee)
    lignes['core.LogActivite'] = _deplacer_les_traces(gardee, absorbee)

    _verifier_les_comptes(gardee, absorbee, avant_gardee, avant_absorbee,
                          avant_journal)

    effets = {
        'hospitalisations': _clore_les_hospitalisations(gardee, actives, choix),
        'rdv_annules': _annuler_les_rdv(doubles, choix),
        'paires_reportees': _reporter_les_paires_ecartees(gardee, absorbee),
    }

    absorbee.fusionne_dans = gardee
    _sauver_sans_trace(absorbee, ['fusionne_dans'])
    _oublier_le_releve(absorbee)

    # Après le comptage : une trace écrite plus tôt se compterait elle-même.
    repris = _libelles(gardee, champs)
    _tracer(gardee, utilisateur, CODE_FUSION,
            f'Fusion : la fiche {absorbee.code_patient} a été absorbée dans '
            f'celle-ci.' + (f' Champs repris : {repris}.' if repris else ''))

    fusion = FusionPatient.all_objects.create(
        centre_id=gardee.centre_id, gardee=gardee, absorbee=absorbee,
        # Les repères recopiés : ils survivront à la suppression définitive
        # des fiches, et c'est par eux que l'ancien code imprimé continuera
        # de mener à la fiche gardée. Voir `patients.resolution`.
        code_absorbee=absorbee.code_patient,
        ancien_identifiant_absorbee=absorbee.ancien_identifiant or '',
        code_gardee=gardee.code_patient,
        utilisateur=utilisateur if utilisateur and utilisateur.is_authenticated else None,
        copie=copie, champs=champs, lignes=lignes, effets=effets)

    # Le relevé de la fiche gardée a changé de contenu : il se reprend après
    # l'enregistrement, comme après n'importe quelle modification de fiche.
    planifier(gardee.pk, gardee.centre)
    _oublier_les_totaux()
    return fusion


def _verifier(gardee, absorbee, choix):
    """Les refus, et les choix qu'on ne peut pas deviner."""
    if gardee.pk == absorbee.pk:
        raise FusionRefusee("Une fiche ne peut pas se fusionner avec elle-même.")
    if absorbee.fusionne_dans_id or gardee.fusionne_dans_id:
        raise FusionRefusee("L'une de ces fiches a déjà été fusionnée.")
    for obstacle in obstacles(gardee, absorbee):
        if obstacle.gravite == 'refus':
            raise FusionRefusee(obstacle.message)
        if obstacle.code == 'deces' and not choix.deces_confirme:
            raise FusionRefusee(
                "Le décès enregistré doit être confirmé avant de fusionner.")
        if obstacle.code == 'hospitalisations' and not choix.hospitalisation_active:
            raise FusionRefusee(
                "Choisissez l'hospitalisation qui reste active.")
    for proposition in propositions(gardee, absorbee):
        if not proposition.obligatoire:
            continue
        retenu = choix.champs.get(proposition.champ, ('', ''))[0]
        if retenu not in ('gardee', 'absorbee', 'manuel'):
            raise FusionRefusee(
                f'Le champ « {proposition.libelle} » demande un choix.')


def _appliquer_les_champs(gardee, absorbee, choix):
    """Écrit les champs retenus sur la fiche gardée. Rend de quoi revenir.

    La date de naissance emporte sa case « approximative » : prendre la date de
    l'autre fiche sans elle ferait d'une estimation une date certaine. La
    photo, elle, se choisit sans que le fichier de l'autre soit jamais
    supprimé — la fiche absorbée reste en base, et son image avec.

    Un champ absent des choix retombe sur le défaut proposé : appelée sans rien
    choisir, la fusion fait ce que l'écran aurait montré.
    """
    par_nom = {f.name: f for f in champs_fusionnables()}
    journal, modifies = {}, []
    for proposition in propositions(gardee, absorbee):
        f = par_nom[proposition.champ]
        retenu, saisi = choix.champs.get(proposition.champ,
                                         (proposition.defaut, proposition.texte))
        avant = _lire(gardee, f)
        valeur = _valeur_retenue(f, gardee, absorbee, retenu, saisi, avant)
        if valeur == avant:
            continue
        setattr(gardee, f.attname, valeur)
        modifies.append(f.attname)
        journal[f.name] = {'choix': retenu or 'gardee',
                           'avant': _en_json(f, avant),
                           'apres': _en_json(f, valeur)}
        if f.name == 'date_naissance' and retenu == 'absorbee':
            journal['date_naissance_approx'] = {
                'choix': 'absorbee',
                'avant': gardee.date_naissance_approx,
                'apres': absorbee.date_naissance_approx}
            gardee.date_naissance_approx = absorbee.date_naissance_approx
            modifies.append('date_naissance_approx')
    if modifies:
        _sauver_sans_trace(gardee, modifies)
    return journal


def _valeur_retenue(f, gardee, absorbee, retenu, saisi, avant):
    if retenu == 'absorbee':
        return _lire(absorbee, f)
    if retenu == 'manuel':
        return f.to_python(saisi) if saisi != '' else ('' if not f.null else None)
    if retenu == 'additionner':
        return additionner(_lire(gardee, f), _lire(absorbee, f))
    return avant


def _deplacer(gardee, absorbee):
    """Change le propriétaire des lignes liées. Rend {table: [pk…]}.

    `update()` et non `save()` : une facture déplacée n'a pas été modifiée, et
    rien ne doit la ré-annoncer aux signaux ni réécrire sa date.
    """
    bouge = {}
    for modele, nom_du_champ, _libelle in liens():
        gestionnaire = getattr(modele, 'all_objects', modele._default_manager)
        pks = list(gestionnaire.filter(**{nom_du_champ: absorbee.pk})
                   .values_list('pk', flat=True))
        if not pks:
            continue
        gestionnaire.filter(pk__in=pks).update(**{nom_du_champ: gardee.pk})
        bouge[f'{modele._meta.app_label}.{modele.__name__}'] = list(pks)
    return bouge


def _type_patient():
    from django.contrib.contenttypes.models import ContentType
    from .models import Patient
    return ContentType.objects.get_for_model(Patient)


def _oublier_les_totaux():
    """Les données rattachées gardées une minute pour le filtre de l'écran.

    Une fusion les déplace : les garder ferait proposer au filtre « aucune
    donnée » des fiches qui viennent d'en recevoir.
    """
    from .liens_patient import oublier_les_totaux
    oublier_les_totaux()


def _sauver_sans_trace(fiche, champs):
    """Enregistre la fiche sans que le journal automatique s'en mêle.

    `_skip_auto_log` est la porte prévue par `core.audit` pour l'appelant qui
    écrit lui-même une trace plus juste. Ici elle est indispensable : la trace
    automatique tomberait entre le comptage d'avant et sa vérification.
    """
    fiche._skip_auto_log = True
    try:
        fiche.save(update_fields=champs)
    finally:
        fiche._skip_auto_log = False


def _libelles(fiche, champs):
    """« Nom, Téléphone » plutôt que « nom, telephone »."""
    noms = []
    for nom in champs or ():
        try:
            noms.append(str(fiche._meta.get_field(nom).verbose_name).capitalize())
        except Exception:
            noms.append(nom)
    return ', '.join(noms)


def _tracer(fiche, utilisateur, code, message):
    from core.views import log_event
    log_event(fiche, utilisateur, message, type='system', code=code,
              module='patients')


def _compter_traces(pk):
    from core.models import LogActivite
    return LogActivite.objects.filter(content_type=_type_patient(),
                                      object_id=pk).count()


def _deplacer_les_traces(gardee, absorbee):
    """L'historique suit la fiche : il est écrit *sur* elle, pas *à propos*."""
    from core.models import LogActivite

    lignes = LogActivite.objects.filter(content_type=_type_patient(),
                                        object_id=absorbee.pk)
    pks = list(lignes.values_list('pk', flat=True))
    if pks:
        LogActivite.objects.filter(pk__in=pks).update(object_id=gardee.pk)
    return pks


def _verifier_les_comptes(gardee, absorbee, avant_gardee, avant_absorbee,
                          avant_journal):
    """Tout ce qui était là doit s'y retrouver — sinon, la transaction retombe."""
    apres_gardee = comptes_par_table([gardee.pk])[gardee.pk]
    apres_absorbee = comptes_par_table([absorbee.pk])[absorbee.pk]
    if apres_absorbee:
        raise FusionIncoherente(
            f'La fiche absorbée porte encore {sum(apres_absorbee.values())} '
            f'ligne(s) après le déplacement : {apres_absorbee}.')
    for cle in set(avant_gardee) | set(avant_absorbee):
        attendu = avant_gardee.get(cle, 0) + avant_absorbee.get(cle, 0)
        if apres_gardee.get(cle, 0) != attendu:
            raise FusionIncoherente(
                f'{cle[1]} : {apres_gardee.get(cle, 0)} ligne(s) après fusion, '
                f'{attendu} attendue(s).')

    avant_g, avant_a = avant_journal
    if _compter_traces(gardee.pk) != avant_g + avant_a:
        raise FusionIncoherente("L'historique ne se retrouve pas en entier.")
    if _compter_traces(absorbee.pk):
        raise FusionIncoherente("La fiche absorbée porte encore de l'historique.")


# ── Les cas particuliers ────────────────────────────────────────────────────

def _clore_les_hospitalisations(gardee, actives, choix):
    """Celles qu'on ne garde pas sont clôturées, leurs lits libérés.

    « Annulée », jamais supprimée : le séjour a eu lieu. L'occupation d'un lit
    se lit sur le statut — rien d'autre à défaire pour que la place se libère.
    """
    from hospitalisation.models import Hospitalisation

    if len({h.patient_id for h in actives}) < 2 or not choix.hospitalisation_active:
        return []
    note = f'Annulée (doublon) : fiche fusionnée dans {gardee.code_patient}.'
    traces = []
    for hospitalisation in actives:
        if hospitalisation.pk == choix.hospitalisation_active:
            continue
        traces.append({'pk': hospitalisation.pk,
                       'statut_avant': hospitalisation.statut,
                       'notes_avant': hospitalisation.notes or '',
                       'chambre': hospitalisation.chambre_id,
                       'lit': hospitalisation.numero_lit})
        Hospitalisation.all_objects.filter(pk=hospitalisation.pk).update(
            statut='annule',
            notes=f'{hospitalisation.notes}\n{note}'.strip()
            if hospitalisation.notes else note)
    return traces


def _annuler_les_rdv(doubles, choix):
    """Les rendez-vous en double que l'on a demandé d'annuler.

    Seuls ceux que le relevé jugeait annulables : une case cochée ne doit pas
    pouvoir écarter un rendez-vous qui porte une consultation ou un registre.
    """
    from .models import RendezVous

    autorises = {d['absorbee'].pk: d['absorbee'] for d in doubles if d['annulable']}
    traces = []
    for pk in choix.rdv_a_annuler:
        rdv = autorises.get(int(pk))
        if rdv is None:
            continue
        note = 'Annulé (doublon) lors de la fusion des fiches.'
        traces.append({'pk': rdv.pk, 'statut_avant': rdv.statut,
                       'notes_avant': rdv.notes or ''})
        RendezVous.all_objects.filter(pk=rdv.pk).update(
            statut='annule',
            notes=f'{rdv.notes}\n{note}'.strip() if rdv.notes else note)
    return traces


def _reporter_les_paires_ecartees(gardee, absorbee):
    """« Pas un doublon » décidé sur la fiche absorbée vaut pour la gardée.

    Reportées et non déplacées : la fiche absorbée garde les siennes, et si on
    défait la fusion chacune retrouve les siennes sans rien à reconstituer.
    """
    from .models import PaireEcartee

    creees = []
    lignes = PaireEcartee.all_objects.filter(
        Q(patient_a=absorbee) | Q(patient_b=absorbee))
    for paire in lignes:
        autre = (paire.patient_b_id if paire.patient_a_id == absorbee.pk
                 else paire.patient_a_id)
        if autre == gardee.pk:
            continue                       # la question ne se pose plus
        a, b = paire_ordonnee(gardee.pk, autre)
        _paire, cree = PaireEcartee.all_objects.get_or_create(
            patient_a_id=a, patient_b_id=b,
            defaults={'utilisateur': paire.utilisateur, 'raison': paire.raison,
                      'centre_id': gardee.centre_id})
        if cree:
            creees.append([a, b])
    return creees


def _oublier_le_releve(fiche):
    """Les paires de la fiche absorbée quittent le relevé tout de suite.

    Le recalcul ciblé le ferait aussi, mais en tâche de fond : l'écran
    montrerait encore le groupe au retour à la liste.
    """
    from .models import DoublonPaire

    DoublonPaire.all_objects.filter(
        Q(patient_a=fiche) | Q(patient_b=fiche)).delete()


# ── Aller et retour entre la base et le journal ─────────────────────────────

def _en_json(champ, valeur):
    if valeur is None or isinstance(valeur, (str, int, float, bool)):
        return valeur
    if isinstance(valeur, (datetime, type_date)):
        return valeur.isoformat()
    return str(valeur)


def _depuis_json(champ, valeur):
    if valeur is None or champ.is_relation:
        return valeur
    if valeur == '' and not isinstance(champ, (models.CharField, models.TextField)):
        return None
    return champ.to_python(valeur)


# ── Défaire une fusion ──────────────────────────────────────────────────────

def fusion_bloquante(fusion):
    """La fusion plus récente qu'il faut défaire d'abord, s'il y en a une.

    Défaire la première d'une chaîne remettrait des lignes à une fiche que la
    seconde a déjà déplacées, et rendrait à la fiche gardée des valeurs
    d'avant la seconde. On refuse, et on dit par laquelle commencer.
    """
    from .models import FusionPatient

    fiches = [fusion.gardee_id, fusion.absorbee_id]
    return (FusionPatient.all_objects
            .filter(annulee_le__isnull=True, date__gt=fusion.date)
            .filter(Q(gardee_id__in=fiches) | Q(absorbee_id__in=fiches))
            .exclude(pk=fusion.pk)
            .select_related('gardee', 'absorbee')
            .order_by('-date').first())


def annuler(fusion, utilisateur=None):
    """Défait une fusion. Rend la liste de ce qui n'a pas pu être rendu."""
    if not fusion.active:
        raise FusionRefusee('Cette fusion a déjà été annulée.')
    if not fusion.annulable:
        # Le journal garde la copie de ce qu'il y avait ; il ne recrée pas le
        # dossier. L'avertissement était affiché avant de supprimer.
        raise FusionRefusee(
            "Une des deux fiches a été supprimée définitivement : cette "
            "fusion ne peut plus être annulée.")
    bloquante = fusion_bloquante(fusion)
    if bloquante is not None:
        raise FusionRefusee(
            'Une fusion plus récente touche ces fiches. Annulez d’abord '
            f'{bloquante.absorbee.code_patient} → {bloquante.gardee.code_patient}, '
            f'du {bloquante.date:%d/%m/%Y à %H:%M}.')
    try:
        with verrou(exclusif=False):
            return _annuler(fusion, utilisateur)
    except RecalculDejaEnCours:
        raise FusionRefusee(
            'Un recalcul complet des doublons est en cours : réessayez dans '
            'un moment.')


def _champs_patient_par_table():
    return {f'{m._meta.app_label}.{m.__name__}': nom for m, nom, _l in liens()}


@transaction.atomic
def _annuler(fusion, utilisateur):
    from core.models import LogActivite
    from .models import PaireEcartee, RendezVous

    gardee, absorbee = fusion.gardee, fusion.absorbee
    retenues, par_table = [], _champs_patient_par_table()

    for table, pks in (fusion.lignes or {}).items():
        if table == 'core.LogActivite' or not pks:
            continue
        nom_du_champ = par_table.get(table)
        if nom_du_champ is None:
            retenues.append(f'{table} : cette table n’existe plus.')
            continue
        modele = apps.get_model(*table.split('.'))
        gestionnaire = getattr(modele, 'all_objects', modele._default_manager)
        # Seules celles qui sont encore là **et** encore à la fiche gardée :
        # une ligne qu'on a déplacée ailleurs depuis ne nous appartient plus.
        encore = list(gestionnaire.filter(pk__in=pks, **{nom_du_champ: gardee.pk})
                      .values_list('pk', flat=True))
        if encore:
            gestionnaire.filter(pk__in=encore).update(**{nom_du_champ: absorbee.pk})
        perdues = len(pks) - len(encore)
        if perdues:
            retenues.append(
                f'{modele._meta.verbose_name} : {perdues} ligne(s) non rendue(s), '
                'supprimée(s) ou déplacée(s) depuis la fusion.')

    traces = (fusion.lignes or {}).get('core.LogActivite') or []
    if traces:
        LogActivite.objects.filter(pk__in=traces, content_type=_type_patient(),
                                   object_id=gardee.pk).update(object_id=absorbee.pk)

    par_nom = {f.name: f for f in gardee._meta.concrete_fields}
    modifies = []
    for nom, trace in (fusion.champs or {}).items():
        f = par_nom.get(nom)
        if f is None:
            continue
        setattr(gardee, f.attname, _depuis_json(f, trace.get('avant')))
        modifies.append(f.attname)
    if modifies:
        _sauver_sans_trace(gardee, modifies)

    for trace in (fusion.effets or {}).get('hospitalisations', []):
        raison = _rouvrir_l_hospitalisation(trace)
        if raison:
            retenues.append(raison)

    for trace in (fusion.effets or {}).get('rdv_annules', []):
        RendezVous.all_objects.filter(pk=trace['pk'], statut='annule').update(
            statut=trace['statut_avant'], notes=trace.get('notes_avant', ''))

    for paire in (fusion.effets or {}).get('paires_reportees', []):
        PaireEcartee.all_objects.filter(patient_a_id=paire[0],
                                        patient_b_id=paire[1]).delete()

    absorbee.fusionne_dans = None
    _sauver_sans_trace(absorbee, ['fusionne_dans'])

    _tracer(gardee, utilisateur, CODE_ANNULATION,
            f'Fusion annulée : la fiche {absorbee.code_patient} a repris ses '
            f'données.')

    fusion.annulee_le = timezone.now()
    fusion.annulee_par = (utilisateur if utilisateur
                          and utilisateur.is_authenticated else None)
    fusion.save(update_fields=['annulee_le', 'annulee_par'])

    planifier(gardee.pk, gardee.centre)
    planifier(absorbee.pk, absorbee.centre)
    _oublier_les_totaux()
    return retenues


def _rouvrir_l_hospitalisation(trace):
    """Rouvre le séjour clôturé, ou dit pourquoi elle ne peut pas."""
    from hospitalisation.models import Hospitalisation

    hospitalisation = Hospitalisation.all_objects.filter(pk=trace['pk']).first()
    if hospitalisation is None:
        return "Une hospitalisation clôturée par la fusion n’existe plus."
    if hospitalisation.statut != 'annule':
        return ''                       # quelqu'un l'a déjà reprise en main
    if trace.get('statut_avant') == 'hospitalise' and trace.get('chambre'):
        occupant = (Hospitalisation.all_objects
                    .filter(chambre_id=trace['chambre'], numero_lit=trace.get('lit'),
                            statut='hospitalise')
                    .exclude(pk=hospitalisation.pk)
                    .select_related('patient').first())
        if occupant is not None:
            return (f'Le séjour {hospitalisation.numero} reste annulé : le lit '
                    f'{trace.get("lit")} est occupé par '
                    f'{occupant.patient.code_patient} depuis la fusion.')
    Hospitalisation.all_objects.filter(pk=hospitalisation.pk).update(
        statut=trace['statut_avant'], notes=trace.get('notes_avant', ''))
    return ''
